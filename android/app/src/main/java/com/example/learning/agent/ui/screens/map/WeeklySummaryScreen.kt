package com.example.learning.agent.ui.screens.map

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.example.learning.agent.data.remote.S2Api
import com.example.learning.agent.data.repository.FeedbackRepository
import com.example.learning.agent.data.repository.S2Cache
import com.example.learning.agent.data.repository.S2Repository
import com.example.learning.agent.data.repository.ThreadPrefs
import com.example.learning.agent.data.repository.TriggerRepository
import com.example.learning.agent.ui.components.FeedbackBottomSheet
import com.example.learning.agent.ui.components.WeeklySummaryCard
import com.example.learning.agent.ui.theme.TekLearningAgentTheme
import kotlinx.coroutines.launch

private data class SummaryFeedbackDraft(
    val summary: S2Api.S2SummaryItem,
    val action: String,
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WeeklySummaryScreen(
    onOpenSummary: (id: String) -> Unit,
    modifier: Modifier = Modifier
) {
    var summaries by remember { mutableStateOf<List<S2Api.S2SummaryItem>>(emptyList()) }
    var isLoading by remember { mutableStateOf(false) }
    var isRefreshing by remember { mutableStateOf(false) }
    var loadError by remember { mutableStateOf<String?>(null) }
    var reprocessingId by remember { mutableStateOf<String?>(null) }
    var feedbackDraft by remember { mutableStateOf<SummaryFeedbackDraft?>(null) }
    var feedbackBySummaryId by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var feedbackSubmittingIds by remember { mutableStateOf<Set<String>>(emptySet()) }
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }
    val context = LocalContext.current.applicationContext

    fun loadFromApi(showRefresh: Boolean = false) {
        if (showRefresh) isRefreshing = true else if (summaries.isEmpty()) isLoading = true
        loadError = null
        scope.launch {
            when (val r = S2Repository.getS2Summaries(limit = 20, threadId = ThreadPrefs.getSelectedThreadId(context))) {
                is S2Repository.Result.Success -> {
                    summaries = r.summaries
                    S2Cache.saveCachedSummaries(context, r.summaries)
                }
                is S2Repository.Result.Error -> {
                    loadError = r.message
                    snackbarHostState.showSnackbar("Error: ${r.message}")
                }
            }
            isLoading = false
            isRefreshing = false
        }
    }

    fun doReprocess(summary: S2Api.S2SummaryItem) {
        val weekStart = summary.extra?.weekStart ?: return
        reprocessingId = summary.id
        scope.launch {
            when (val jobR = S2Repository.enqueueS2Job(weekStart)) {
                is S2Repository.ReprocessResult.Success -> {
                    when (val triggerR = TriggerRepository.triggerWorker()) {
                        is TriggerRepository.Result.Success -> {
                            if (triggerR.processed) {
                                snackbarHostState.showSnackbar("Re-generating… Refreshing in a moment.")
                                kotlinx.coroutines.delay(2000)
                                loadFromApi(showRefresh = true)
                            } else {
                                snackbarHostState.showSnackbar("Job queued. Tap Refresh or wait for worker.")
                                loadFromApi(showRefresh = true)
                            }
                        }
                        is TriggerRepository.Result.Error ->
                            snackbarHostState.showSnackbar("Queued but trigger failed: ${triggerR.message}")
                    }
                }
                is S2Repository.ReprocessResult.Error ->
                    snackbarHostState.showSnackbar("Error: ${jobR.message}")
            }
            reprocessingId = null
        }
    }

    LaunchedEffect(Unit) {
        val cached = S2Cache.getCachedSummaries(context)
        if (!cached.isNullOrEmpty()) {
            summaries = cached
        }
        loadFromApi()
    }

    Scaffold(snackbarHost = { SnackbarHost(snackbarHostState) }) { paddingValues ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            when {
                isLoading && summaries.isEmpty() -> {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(24.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            CircularProgressIndicator()
                            Spacer(modifier = Modifier.height(16.dp))
                            Text(
                                text = "Loading weekly summaries…",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
                loadError != null && summaries.isEmpty() -> {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(24.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                text = "Could not load summaries",
                                style = MaterialTheme.typography.titleSmall,
                                color = MaterialTheme.colorScheme.error
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(
                                text = loadError ?: "",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(modifier = Modifier.height(16.dp))
                            TextButton(onClick = { loadFromApi() }) {
                                Text("Retry")
                            }
                        }
                    }
                }
                summaries.isEmpty() -> {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(24.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                text = "No weekly summaries yet",
                                style = MaterialTheme.typography.titleSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(
                                text = "Summaries are generated weekly. Add documents in Feed and wait for the next run, or trigger from the server.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(modifier = Modifier.height(16.dp))
                            Button(onClick = { loadFromApi() }) {
                                Text("Refresh")
                            }
                        }
                    }
                }
                else -> {
                    PullToRefreshBox(
                        isRefreshing = isRefreshing,
                        onRefresh = { loadFromApi(showRefresh = true) },
                        modifier = Modifier.fillMaxSize()
                    ) {
                        LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(16.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            items(summaries) { summary ->
                                WeeklySummaryCard(
                                    summary = summary,
                                    onOpen = { onOpenSummary(summary.id) },
                                    onReprocess = { doReprocess(summary) },
                                    onThumbsUp = {
                                        if (summary.id !in feedbackSubmittingIds) {
                                            feedbackDraft = SummaryFeedbackDraft(summary, FeedbackRepository.ACTION_THUMBS_UP)
                                        }
                                    },
                                    onThumbsDown = {
                                        if (summary.id !in feedbackSubmittingIds) {
                                            feedbackDraft = SummaryFeedbackDraft(summary, FeedbackRepository.ACTION_THUMBS_DOWN)
                                        }
                                    },
                                    feedbackAction = feedbackBySummaryId[summary.id],
                                    feedbackSubmitting = summary.id in feedbackSubmittingIds,
                                    isReprocessing = reprocessingId == summary.id
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    if (feedbackDraft != null) {
        val draft = feedbackDraft!!
        FeedbackBottomSheet(
            title = if (draft.action == FeedbackRepository.ACTION_THUMBS_UP) {
                "What worked well?"
            } else {
                "What should improve?"
            },
            reasons = FeedbackRepository.SUMMARY_S2_REASONS,
            onDismiss = { feedbackDraft = null },
            onSubmit = { reasons, comment ->
                val previous = feedbackBySummaryId[draft.summary.id]
                feedbackBySummaryId = feedbackBySummaryId + (draft.summary.id to draft.action)
                feedbackSubmittingIds = feedbackSubmittingIds + draft.summary.id
                feedbackDraft = null
                scope.launch {
                    when (val result = FeedbackRepository.submit(
                        targetType = FeedbackRepository.TARGET_SUMMARY_S2,
                        targetId = draft.summary.id,
                        action = draft.action,
                        reasons = reasons,
                        comment = comment,
                        weekStart = draft.summary.extra?.weekStart,
                        meta = mapOf(
                            "topic_name" to draft.summary.extra?.topicName,
                            "week_start" to draft.summary.extra?.weekStart,
                            "tldr" to draft.summary.tldr,
                        )
                    )) {
                        is FeedbackRepository.Result.Success ->
                            snackbarHostState.showSnackbar("Feedback saved")
                        is FeedbackRepository.Result.Error -> {
                            feedbackBySummaryId = if (previous == null) {
                                feedbackBySummaryId - draft.summary.id
                            } else {
                                feedbackBySummaryId + (draft.summary.id to previous)
                            }
                            snackbarHostState.showSnackbar("Could not save feedback: ${result.message}")
                        }
                    }
                    feedbackSubmittingIds = feedbackSubmittingIds - draft.summary.id
                }
            }
        )
    }
}
