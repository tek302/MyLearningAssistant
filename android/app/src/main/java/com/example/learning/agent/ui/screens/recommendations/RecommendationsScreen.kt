package com.example.learning.agent.ui.screens.recommendations

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.TrendingDown
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.learning.agent.data.models.Recommendation
import com.example.learning.agent.data.remote.KeywordsApi
import com.example.learning.agent.data.remote.ThreadsApi
import com.example.learning.agent.data.repository.FeedbackRepository
import com.example.learning.agent.data.repository.IngestRepository
import com.example.learning.agent.data.repository.KeywordsRepository
import com.example.learning.agent.data.repository.RecommendationsRepository
import com.example.learning.agent.data.repository.ThreadPrefs
import com.example.learning.agent.data.repository.ThreadsRepository
import com.example.learning.agent.ui.components.AddKeywordDialog
import com.example.learning.agent.ui.components.FeedbackBottomSheet
import com.example.learning.agent.ui.components.KeywordProfileManageList
import com.example.learning.agent.ui.components.RecommendationCard
import com.example.learning.agent.ui.theme.TekLearningAgentTheme
import kotlinx.coroutines.launch
import java.util.Calendar

private data class RecommendationFeedbackDraft(
    val recommendation: Recommendation,
    val action: String,
)

private fun recommendationMatchesKeyword(rec: Recommendation, keyword: String): Boolean {
    val k = keyword.lowercase()
    if (rec.title.lowercase().contains(k)) return true
    val abs = rec.abstract?.lowercase().orEmpty()
    return abs.contains(k)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecommendationsScreen(
    modifier: Modifier = Modifier
) {
    var selectedWeek by remember { mutableStateOf("All") }
    var selectedKeywordFilter by remember { mutableStateOf<String?>(null) }

    var keywordItems by remember { mutableStateOf<List<KeywordsApi.KeywordItem>>(emptyList()) }
    var suggestions by remember { mutableStateOf<List<KeywordsApi.SuggestionItem>>(emptyList()) }

    var recommendations by remember { mutableStateOf<List<Recommendation>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var isRefreshing by remember { mutableStateOf(false) }
    var loadError by remember { mutableStateOf<String?>(null) }
    var processInProgress by remember { mutableStateOf<String?>(null) }
    var removeInProgress by remember { mutableStateOf<String?>(null) }
    var feedbackDraft by remember { mutableStateOf<RecommendationFeedbackDraft?>(null) }
    var feedbackByRecommendationId by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var feedbackSubmittingIds by remember { mutableStateOf<Set<String>>(emptySet()) }

    var showKeywordManageSheet by remember { mutableStateOf(false) }
    var showAddKeywordDialog by remember { mutableStateOf(false) }
    val context = LocalContext.current.applicationContext
    var threads by remember { mutableStateOf<List<ThreadsApi.InterestThreadItem>>(emptyList()) }
    var selectedThreadId by remember { mutableStateOf<String?>(ThreadPrefs.getSelectedThreadId(context)) }
    var threadMenuExpanded by remember { mutableStateOf(false) }
    var showCreateThreadDialog by remember { mutableStateOf(false) }
    var newThreadName by remember { mutableStateOf("") }
    var newThreadDescription by remember { mutableStateOf("") }
    var isCreatingThread by remember { mutableStateOf(false) }
    var showArchiveConfirmDialog by remember { mutableStateOf(false) }
    var isArchivingThread by remember { mutableStateOf(false) }

    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    suspend fun trackRecommendationAction(
        recommendation: Recommendation,
        action: String
    ) {
        FeedbackRepository.submit(
            targetType = FeedbackRepository.TARGET_RECOMMENDATION,
            targetId = recommendation.id,
            action = action,
            reasons = emptyList(),
            comment = null,
            weekStart = recommendation.weekStart,
            meta = mapOf(
                "title" to recommendation.title,
                "url" to recommendation.url,
                "source" to recommendation.source,
                "topic_name" to recommendation.topicName,
                "week_start" to recommendation.weekStart,
            )
        )
    }

    val filterChipsKeywords = remember(keywordItems) {
        keywordItems
            .filter { it.status == "active" || it.status == "declining" }
            .sortedByDescending { it.status == "active" }
    }

    val displayedRecommendations = remember(recommendations, selectedKeywordFilter) {
        val f = selectedKeywordFilter
        if (f.isNullOrBlank()) recommendations
        else recommendations.filter { recommendationMatchesKeyword(it, f) }
    }

    fun weekStartForLabel(label: String): String? = when (label) {
        "This Week" -> getWeekStartMonday(0)
        "Last Week" -> getWeekStartMonday(-1)
        else -> null
    }

    fun loadRecommendations(showRefresh: Boolean = false) {
        if (showRefresh) {
            if (isRefreshing) return
            isRefreshing = true
        } else {
            if (isLoading && recommendations.isNotEmpty()) return
            isLoading = true
        }
        loadError = null
        scope.launch {
            try {
                when (val kwResult = KeywordsRepository.listKeywords()) {
                    is KeywordsRepository.Result.Success -> keywordItems = kwResult.data.items
                    is KeywordsRepository.Result.Error -> { /* keep previous */ }
                }
                when (val sugResult = KeywordsRepository.listSuggestions(status = "pending")) {
                    is KeywordsRepository.Result.Success -> suggestions = sugResult.data
                    is KeywordsRepository.Result.Error -> { /* keep previous */ }
                }
                val weekStart = weekStartForLabel(selectedWeek)
                when (val r = RecommendationsRepository.list(
                    weekStart = weekStart,
                    topicName = null,
                    threadId = selectedThreadId,
                    limit = 50
                )) {
                    is RecommendationsRepository.ListResult.Success -> {
                        recommendations = r.items
                    }
                    is RecommendationsRepository.ListResult.Error -> {
                        loadError = r.message
                        snackbarHostState.showSnackbar("Error: ${r.message}")
                    }
                }
            } finally {
                isLoading = false
                isRefreshing = false
            }
        }
    }

    suspend fun refreshThreads() {
        when (val tr = ThreadsRepository.refreshSelection(context)) {
            is ThreadsRepository.Result.Success -> {
                threads = tr.threads
                selectedThreadId = ThreadPrefs.getSelectedThreadId(context)
            }
            is ThreadsRepository.Result.Error -> { /* keep previous */ }
        }
    }

    LaunchedEffect(Unit) {
        refreshThreads()
    }

    LaunchedEffect(selectedWeek, selectedThreadId) {
        loadRecommendations()
    }

    PullToRefreshBox(
        isRefreshing = isRefreshing,
        onRefresh = { loadRecommendations(showRefresh = true) },
        modifier = modifier.fillMaxSize()
    ) {
        Scaffold(
            snackbarHost = { SnackbarHost(snackbarHostState) },
            floatingActionButton = {
                ExtendedFloatingActionButton(
                    onClick = { showKeywordManageSheet = true },
                    icon = { Icon(Icons.Default.Settings, contentDescription = null) },
                    text = { Text("Keywords") }
                )
            }
        ) { paddingValues ->
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues)
                    .padding(16.dp)
            ) {
                if (threads.isNotEmpty()) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(bottom = 12.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        ExposedDropdownMenuBox(
                            expanded = threadMenuExpanded,
                            onExpandedChange = { threadMenuExpanded = it },
                            modifier = Modifier.weight(1f)
                        ) {
                            OutlinedTextField(
                                value = threads.find { it.id == selectedThreadId }?.name ?: "Thread",
                                onValueChange = {},
                                readOnly = true,
                                label = { Text("Thread") },
                                trailingIcon = {
                                    ExposedDropdownMenuDefaults.TrailingIcon(expanded = threadMenuExpanded)
                                },
                                modifier = Modifier.fillMaxWidth().menuAnchor()
                            )
                            ExposedDropdownMenu(
                                expanded = threadMenuExpanded,
                                onDismissRequest = { threadMenuExpanded = false }
                            ) {
                                threads.forEach { t ->
                                    DropdownMenuItem(
                                        text = { Text(t.name) },
                                        onClick = {
                                            selectedThreadId = t.id
                                            ThreadPrefs.setSelectedThreadId(context, t.id)
                                            threadMenuExpanded = false
                                        }
                                    )
                                }
                            }
                        }
                        TextButton(onClick = { showCreateThreadDialog = true }) {
                            Text("Manage")
                        }
                    }
                }

                var expandedWeek by remember { mutableStateOf(false) }
                ExposedDropdownMenuBox(
                    expanded = expandedWeek,
                    onExpandedChange = { expandedWeek = !expandedWeek },
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 12.dp)
                ) {
                    OutlinedTextField(
                        value = selectedWeek,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Time Range") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expandedWeek) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor()
                    )
                    ExposedDropdownMenu(
                        expanded = expandedWeek,
                        onDismissRequest = { expandedWeek = false }
                    ) {
                        listOf("All", "This Week", "Last Week").forEach { week ->
                            DropdownMenuItem(
                                text = { Text(week) },
                                onClick = {
                                    selectedWeek = week
                                    expandedWeek = false
                                }
                            )
                        }
                    }
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        "Filter by keyword",
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    TextButton(onClick = { showKeywordManageSheet = true }) {
                        Text("Manage")
                    }
                }

                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .horizontalScroll(rememberScrollState())
                        .padding(bottom = 12.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    FilterChip(
                        selected = selectedKeywordFilter == null,
                        onClick = { selectedKeywordFilter = null },
                        label = { Text("All") }
                    )
                    filterChipsKeywords.forEach { kw ->
                        val label = kw.keyword.let { t ->
                            if (t.length > 22) t.take(22) + "…" else t
                        }
                        FilterChip(
                            selected = selectedKeywordFilter == kw.keyword,
                            onClick = {
                                selectedKeywordFilter =
                                    if (selectedKeywordFilter == kw.keyword) null else kw.keyword
                            },
                            label = { Text(label) },
                            leadingIcon = if (kw.status == "declining") {
                                {
                                    Icon(
                                        Icons.Filled.TrendingDown,
                                        contentDescription = null,
                                        modifier = Modifier.size(16.dp)
                                    )
                                }
                            } else null
                        )
                    }
                    if (filterChipsKeywords.isEmpty()) {
                        FilledTonalButton(
                            onClick = { showAddKeywordDialog = true },
                            contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)
                        ) {
                            Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(6.dp))
                            Text("Add keyword")
                        }
                    }
                }

                if (suggestions.isNotEmpty()) {
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(bottom = 12.dp),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.35f)
                        )
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    "${suggestions.size} new keyword suggestions",
                                    style = MaterialTheme.typography.titleSmall
                                )
                                Text(
                                    "Open Manage to accept or skip.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                            TextButton(onClick = { showKeywordManageSheet = true }) {
                                Text("Review")
                            }
                        }
                    }
                }

                when {
                    isLoading && recommendations.isEmpty() -> {
                        Box(
                            modifier = Modifier.fillMaxSize(),
                            contentAlignment = Alignment.Center
                        ) {
                            CircularProgressIndicator()
                        }
                    }
                    loadError != null && recommendations.isEmpty() -> {
                        Box(
                            modifier = Modifier.fillMaxSize(),
                            contentAlignment = Alignment.Center
                        ) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Text(
                                    text = loadError ?: "Error",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.error
                                )
                                Spacer(modifier = Modifier.height(8.dp))
                                Button(onClick = { loadRecommendations() }) {
                                    Icon(Icons.Default.Refresh, contentDescription = null)
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Text("Retry")
                                }
                            }
                        }
                    }
                    recommendations.isEmpty() -> {
                        Box(
                            modifier = Modifier.fillMaxSize(),
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                text = "No recommendations yet. Add keywords and complete a weekly summary to get arXiv suggestions.",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                    displayedRecommendations.isEmpty() -> {
                        Box(
                            modifier = Modifier.fillMaxSize(),
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                text = "No papers match \"$selectedKeywordFilter\" in title or abstract. Try another keyword or All.",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                    else -> {
                        LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(vertical = 8.dp)
                        ) {
                            items(displayedRecommendations) { rec ->
                                RecommendationCard(
                                    recommendation = rec,
                                    onThumbsUp = {
                                        if (rec.id !in feedbackSubmittingIds) {
                                            feedbackDraft = RecommendationFeedbackDraft(
                                                rec,
                                                FeedbackRepository.ACTION_THUMBS_UP
                                            )
                                        }
                                    },
                                    onThumbsDown = {
                                        if (rec.id !in feedbackSubmittingIds) {
                                            feedbackDraft = RecommendationFeedbackDraft(
                                                rec,
                                                FeedbackRepository.ACTION_THUMBS_DOWN
                                            )
                                        }
                                    },
                                    feedbackAction = feedbackByRecommendationId[rec.id],
                                    feedbackSubmitting = rec.id in feedbackSubmittingIds,
                                    onProcess = {
                                        if (processInProgress == rec.id) return@RecommendationCard
                                        processInProgress = rec.id
                                        scope.launch {
                                            trackRecommendationAction(rec, FeedbackRepository.ACTION_PROCESS)
                                            when (val ingest = IngestRepository.ingestUrl(rec.url, rec.title, ThreadPrefs.getSelectedThreadId(context))) {
                                                is IngestRepository.Result.Success -> {
                                                    val deleted = RecommendationsRepository.delete(rec.id)
                                                    if (deleted) {
                                                        recommendations = recommendations - rec
                                                        snackbarHostState.showSnackbar("Queued for ingest. Removed from list.")
                                                    } else {
                                                        snackbarHostState.showSnackbar("Queued for ingest. Could not remove from list.")
                                                    }
                                                }
                                                is IngestRepository.Result.Error -> {
                                                    snackbarHostState.showSnackbar("Ingest failed: ${ingest.message}")
                                                }
                                            }
                                            processInProgress = null
                                        }
                                    },
                                    onRemove = {
                                        if (removeInProgress == rec.id) return@RecommendationCard
                                        removeInProgress = rec.id
                                        scope.launch {
                                            trackRecommendationAction(rec, FeedbackRepository.ACTION_REMOVE)
                                            val deleted = RecommendationsRepository.delete(rec.id)
                                            if (deleted) {
                                                recommendations = recommendations - rec
                                                snackbarHostState.showSnackbar("Removed from list.")
                                            } else {
                                                snackbarHostState.showSnackbar("Could not remove.")
                                            }
                                            removeInProgress = null
                                        }
                                    }
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    if (showCreateThreadDialog) {
        AlertDialog(
            onDismissRequest = {
                if (!isCreatingThread && !isArchivingThread) showCreateThreadDialog = false
            },
            title = { Text("Manage thread") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedTextField(
                        value = newThreadName,
                        onValueChange = { newThreadName = it },
                        singleLine = true,
                        label = { Text("New thread name") },
                        enabled = !isCreatingThread
                    )
                    OutlinedTextField(
                        value = newThreadDescription,
                        onValueChange = { newThreadDescription = it },
                        label = { Text("Description (optional)") },
                        enabled = !isCreatingThread
                    )
                    FilledTonalButton(
                        onClick = {
                            scope.launch {
                                isCreatingThread = true
                                when (val result = ThreadsRepository.createThread(
                                    context = context,
                                    name = newThreadName,
                                    description = newThreadDescription,
                                    selectWhenCreated = true
                                )) {
                                    is ThreadsRepository.CreateResult.Success -> {
                                        refreshThreads()
                                        loadRecommendations()
                                        newThreadName = ""
                                        newThreadDescription = ""
                                        snackbarHostState.showSnackbar("Created thread: ${result.thread.name}")
                                    }
                                    is ThreadsRepository.CreateResult.Error -> {
                                        snackbarHostState.showSnackbar("Error: ${result.message}")
                                    }
                                }
                                isCreatingThread = false
                            }
                        },
                        enabled = !isCreatingThread && newThreadName.trim().isNotEmpty()
                    ) {
                        Text("Create thread")
                    }

                    val selected = threads.find { it.id == selectedThreadId }
                    val canArchive = selected != null && !selected.isDefault
                    OutlinedButton(
                        onClick = { showArchiveConfirmDialog = true },
                        enabled = canArchive && !isArchivingThread
                    ) {
                        Text(if (selected?.isDefault == true) "Default thread cannot be archived" else "Archive current thread")
                    }
                }
            },
            confirmButton = {
                TextButton(
                    enabled = !isCreatingThread && !isArchivingThread,
                    onClick = { showCreateThreadDialog = false }
                ) { Text("Done") }
            }
        )
    }

    if (showArchiveConfirmDialog) {
        val selected = threads.find { it.id == selectedThreadId }
        AlertDialog(
            onDismissRequest = {
                if (!isArchivingThread) showArchiveConfirmDialog = false
            },
            title = { Text("Archive thread") },
            text = { Text("Archive '${selected?.name ?: "this thread"}'? This hides it from active lists.") },
            confirmButton = {
                TextButton(
                    enabled = selected != null && !isArchivingThread,
                    onClick = {
                        val thread = selected ?: return@TextButton
                        scope.launch {
                            isArchivingThread = true
                            when (val result = ThreadsRepository.archiveThread(context, thread.id)) {
                                is ThreadsRepository.ArchiveResult.Success -> {
                                    refreshThreads()
                                    loadRecommendations()
                                    snackbarHostState.showSnackbar("Archived thread: ${thread.name}")
                                    showArchiveConfirmDialog = false
                                    showCreateThreadDialog = false
                                }
                                is ThreadsRepository.ArchiveResult.Error -> {
                                    snackbarHostState.showSnackbar("Error: ${result.message}")
                                }
                            }
                            isArchivingThread = false
                        }
                    }
                ) { Text("Archive") }
            },
            dismissButton = {
                TextButton(
                    enabled = !isArchivingThread,
                    onClick = { showArchiveConfirmDialog = false }
                ) { Text("Cancel") }
            }
        )
    }

    if (showKeywordManageSheet) {
        ModalBottomSheet(
            onDismissRequest = { showKeywordManageSheet = false },
            sheetState = sheetState
        ) {
            Column(Modifier.fillMaxWidth()) {
                Text(
                    "Keywords & suggestions",
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                )
                KeywordProfileManageList(
                    keywords = keywordItems,
                    suggestions = suggestions,
                    onAcceptSuggestion = { suggestion ->
                        scope.launch {
                            when (val r = KeywordsRepository.acceptSuggestion(suggestion.id)) {
                                is KeywordsRepository.Result.Success -> {
                                    suggestions = suggestions.filter { it.id != suggestion.id }
                                    when (val kwResult = KeywordsRepository.listKeywords()) {
                                        is KeywordsRepository.Result.Success ->
                                            keywordItems = kwResult.data.items
                                        else -> {}
                                    }
                                    snackbarHostState.showSnackbar("Added: ${suggestion.keyword}")
                                }
                                is KeywordsRepository.Result.Error ->
                                    snackbarHostState.showSnackbar("Failed: ${r.message}")
                            }
                        }
                    },
                    onRejectSuggestion = { suggestion ->
                        scope.launch {
                            when (val r = KeywordsRepository.rejectSuggestion(suggestion.id)) {
                                is KeywordsRepository.Result.Success -> {
                                    suggestions = suggestions.filter { it.id != suggestion.id }
                                    snackbarHostState.showSnackbar("Skipped: ${suggestion.keyword}")
                                }
                                is KeywordsRepository.Result.Error ->
                                    snackbarHostState.showSnackbar("Failed: ${r.message}")
                            }
                        }
                    },
                    onArchiveKeyword = { kw ->
                        scope.launch {
                            when (KeywordsRepository.archiveKeyword(kw.id)) {
                                is KeywordsRepository.Result.Success -> {
                                    keywordItems = keywordItems.filter { it.id != kw.id }
                                    if (selectedKeywordFilter == kw.keyword) selectedKeywordFilter = null
                                    snackbarHostState.showSnackbar("Archived: ${kw.keyword}")
                                }
                                is KeywordsRepository.Result.Error ->
                                    snackbarHostState.showSnackbar("Could not archive")
                            }
                        }
                    }
                )
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    horizontalArrangement = Arrangement.End
                ) {
                    Button(onClick = { showAddKeywordDialog = true }) {
                        Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(8.dp))
                        Text("Add keyword")
                    }
                }
            }
        }
    }

    if (showAddKeywordDialog) {
        AddKeywordDialog(
            onDismiss = { showAddKeywordDialog = false },
            onAdd = { keyword ->
                showAddKeywordDialog = false
                scope.launch {
                    when (val r = KeywordsRepository.createKeyword(keyword)) {
                        is KeywordsRepository.Result.Success -> {
                            when (val kwResult = KeywordsRepository.listKeywords()) {
                                is KeywordsRepository.Result.Success ->
                                    keywordItems = kwResult.data.items
                                else -> {}
                            }
                            snackbarHostState.showSnackbar("Added: $keyword")
                        }
                        is KeywordsRepository.Result.Error -> {
                            snackbarHostState.showSnackbar(
                                if ("409" in r.message || "already exists" in r.message.lowercase())
                                    "Keyword already exists"
                                else "Failed: ${r.message}"
                            )
                        }
                    }
                }
            }
        )
    }

    if (feedbackDraft != null) {
        val draft = feedbackDraft!!
        FeedbackBottomSheet(
            title = if (draft.action == FeedbackRepository.ACTION_THUMBS_UP) {
                "What did you like?"
            } else {
                "What was off?"
            },
            reasons = FeedbackRepository.RECOMMENDATION_REASONS,
            onDismiss = { feedbackDraft = null },
            onSubmit = { reasons, comment ->
                val previous = feedbackByRecommendationId[draft.recommendation.id]
                feedbackByRecommendationId = feedbackByRecommendationId + (draft.recommendation.id to draft.action)
                feedbackSubmittingIds = feedbackSubmittingIds + draft.recommendation.id
                feedbackDraft = null
                scope.launch {
                    when (val result = FeedbackRepository.submit(
                        targetType = FeedbackRepository.TARGET_RECOMMENDATION,
                        targetId = draft.recommendation.id,
                        action = draft.action,
                        reasons = reasons,
                        comment = comment,
                        weekStart = draft.recommendation.weekStart,
                        meta = mapOf(
                            "title" to draft.recommendation.title,
                            "url" to draft.recommendation.url,
                            "source" to draft.recommendation.source,
                            "topic_name" to draft.recommendation.topicName,
                            "week_start" to draft.recommendation.weekStart,
                        )
                    )) {
                        is FeedbackRepository.Result.Success ->
                            snackbarHostState.showSnackbar("Feedback saved")
                        is FeedbackRepository.Result.Error -> {
                            feedbackByRecommendationId = if (previous == null) {
                                feedbackByRecommendationId - draft.recommendation.id
                            } else {
                                feedbackByRecommendationId + (draft.recommendation.id to previous)
                            }
                            snackbarHostState.showSnackbar("Could not save feedback: ${result.message}")
                        }
                    }
                    feedbackSubmittingIds = feedbackSubmittingIds - draft.recommendation.id
                }
            }
        )
    }
}

/** Returns Monday of the week as YYYY-MM-DD. offsetWeeks 0 = this week, -1 = last week. */
private fun getWeekStartMonday(offsetWeeks: Int): String {
    val cal = Calendar.getInstance()
    cal.firstDayOfWeek = Calendar.MONDAY
    cal.set(Calendar.DAY_OF_WEEK, Calendar.MONDAY)
    cal.add(Calendar.WEEK_OF_YEAR, offsetWeeks)
    val y = cal.get(Calendar.YEAR)
    val m = cal.get(Calendar.MONTH) + 1
    val d = cal.get(Calendar.DAY_OF_MONTH)
    return "%04d-%02d-%02d".format(y, m, d)
}

@Preview(showBackground = true)
@Composable
fun RecommendationsScreenPreview() {
    TekLearningAgentTheme {
        RecommendationsScreen()
    }
}
