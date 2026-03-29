package com.example.learning.agent.ui.screens.ask

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ThumbDown
import androidx.compose.material.icons.filled.ThumbUp
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.learning.agent.BuildConfig
import com.example.learning.agent.R
import com.example.learning.agent.data.remote.ApiClient
import com.example.learning.agent.data.remote.DocumentsApi
import com.example.learning.agent.data.remote.RagApi
import com.example.learning.agent.data.repository.DocumentsRepository
import com.example.learning.agent.data.repository.FeedbackRepository
import com.example.learning.agent.data.repository.OnboardingPrefs
import com.example.learning.agent.ui.theme.TekLearningAgentTheme
import kotlinx.coroutines.launch
import java.util.UUID

private const val MAX_CITATION_QUOTE_PREVIEW_CHARS = 180

@Composable
fun AskScreen(
    selectedDocumentId: String? = null,
    selectedDocumentTitle: String? = null,
    onDocumentSelect: (id: String, title: String?) -> Unit = { _, _ -> },
    onDocumentDeselect: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    var query by remember { mutableStateOf("") }
    var answer by remember { mutableStateOf("") }
    var citations by remember { mutableStateOf<List<RagApi.CitationItem>>(emptyList()) }
    var runId by remember { mutableStateOf<String?>(null) }
    var feedbackAction by remember { mutableStateOf<String?>(null) }
    var selectedFeedbackReasons by remember { mutableStateOf<Set<String>>(emptySet()) }
    var feedbackComment by remember { mutableStateOf("") }
    var feedbackSubmitting by remember { mutableStateOf(false) }
    var isLoading by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var showDocumentPicker by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }
    val context = LocalContext.current.applicationContext
    val clipboardManager = LocalClipboardManager.current
    val uriHandler = LocalUriHandler.current
    val openLinkFailedMessage = stringResource(R.string.ask_open_link_failed)
    val runIdCopiedMessage = stringResource(R.string.ask_run_id_copied)
    val feedbackSubmitSuccessMessage = stringResource(R.string.ask_feedback_submit_success)
    val feedbackSubmitFailedMessage = stringResource(R.string.ask_feedback_submit_failed)

    Scaffold(snackbarHost = { SnackbarHost(snackbarHostState) }) { paddingValues ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(paddingValues)
                .padding(16.dp)
        ) {
            // Current document banner — shows which doc is used for RAG; can clear or change selection
            Surface(
                modifier = Modifier.fillMaxWidth(),
                color = if (selectedDocumentId != null)
                    MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.6f)
                else
                    MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f),
                shape = MaterialTheme.shapes.small
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = if (selectedDocumentId != null)
                                "Asking about: ${(selectedDocumentTitle?.takeIf { it.isNotBlank() } ?: "Document").take(50)}${if ((selectedDocumentTitle?.length ?: 0) > 50) "…" else ""}"
                            else
                                "No document selected — answers will use all your documents",
                            style = MaterialTheme.typography.bodySmall,
                            color = if (selectedDocumentId != null)
                                MaterialTheme.colorScheme.onPrimaryContainer
                            else
                                MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        if (selectedDocumentId != null && selectedDocumentTitle != null &&
                            (selectedDocumentTitle.contains("/") || selectedDocumentTitle.endsWith(".pdf"))
                        ) {
                            Text(
                                text = "Title not available",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.8f)
                            )
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        TextButton(onClick = { showDocumentPicker = true }) {
                            Text(if (selectedDocumentId != null) "Change" else "Select", style = MaterialTheme.typography.labelMedium)
                        }
                        if (selectedDocumentId != null) {
                            TextButton(onClick = onDocumentDeselect) {
                                Text("Clear", style = MaterialTheme.typography.labelMedium)
                            }
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Query input
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                label = { Text("Enter your question") },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 16.dp),
                singleLine = false,
                maxLines = 4
            )

            // Ask button
            Button(
                onClick = {
                    if (query.isBlank()) return@Button
                    scope.launch {
                        isLoading = true
                        errorMessage = null
                        citations = emptyList()
                        runId = null
                        feedbackAction = null
                        selectedFeedbackReasons = emptySet()
                        feedbackComment = ""
                        try {
                            val request = RagApi.RagAnswerRequest(
                                query = query.trim(),
                                top_k = 8,
                                document_id = selectedDocumentId,
                                include_citations = true
                            )
                            val response = ApiClient.ragApi.answer(request)
                            if (response.isSuccessful) {
                                val body = response.body()
                                answer = body?.answer ?: ""
                                citations = body?.citations ?: emptyList()
                                runId = extractRunId(body?.meta) ?: UUID.randomUUID().toString()
                                OnboardingPrefs.markFirstAskCompletedSync(context)
                            } else {
                                errorMessage = "HTTP ${response.code()}: ${response.message()}"
                                snackbarHostState.showSnackbar(errorMessage!!)
                            }
                        } catch (e: Exception) {
                            errorMessage = e.message ?: "Network error"
                            snackbarHostState.showSnackbar(errorMessage!!)
                        }
                        isLoading = false
                    }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 24.dp),
                enabled = !isLoading
            ) {
                Text(if (isLoading) "Asking…" else "Ask")
            }

            // Answer area
            if (answer.isNotEmpty()) {
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 16.dp),
                    elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp)
                    ) {
                        Text(
                            text = stringResource(R.string.ask_answer_title),
                            style = MaterialTheme.typography.titleMedium,
                            modifier = Modifier.padding(bottom = 8.dp)
                        )
                        Text(
                            text = answer,
                            style = MaterialTheme.typography.bodyLarge
                        )

                        Spacer(modifier = Modifier.height(16.dp))
                        Text(
                            text = stringResource(R.string.ask_sources_title),
                            style = MaterialTheme.typography.titleSmall
                        )
                        Spacer(modifier = Modifier.height(8.dp))

                        if (citations.isEmpty()) {
                            Text(
                                text = stringResource(R.string.ask_sources_empty),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        } else {
                            citations.forEach { citation ->
                                CitationItemView(
                                    citation = citation,
                                    onOpenUrl = { url ->
                                        scope.launch {
                                            try {
                                                uriHandler.openUri(url)
                                            } catch (_: Exception) {
                                                snackbarHostState.showSnackbar(
                                                    message = openLinkFailedMessage
                                                )
                                            }
                                        }
                                    }
                                )
                            }
                        }

                        if (BuildConfig.DEBUG && !runId.isNullOrBlank()) {
                            Spacer(modifier = Modifier.height(12.dp))
                            Text(
                                text = stringResource(R.string.ask_run_id_label, runId ?: ""),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.clickable {
                                    clipboardManager.setText(AnnotatedString(runId!!))
                                    scope.launch {
                                        snackbarHostState.showSnackbar(runIdCopiedMessage)
                                    }
                                }
                            )
                        }

                        Spacer(modifier = Modifier.height(16.dp))
                        Text(
                            text = stringResource(R.string.ask_feedback_title),
                            style = MaterialTheme.typography.titleSmall
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            IconButton(
                                onClick = {
                                    feedbackAction = FeedbackRepository.ACTION_THUMBS_UP
                                    selectedFeedbackReasons = emptySet()
                                },
                                enabled = !feedbackSubmitting
                            ) {
                                Icon(
                                    imageVector = Icons.Default.ThumbUp,
                                    contentDescription = stringResource(R.string.ask_feedback_thumbs_up),
                                    tint = if (feedbackAction == FeedbackRepository.ACTION_THUMBS_UP)
                                        MaterialTheme.colorScheme.primary
                                    else
                                        MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                            IconButton(
                                onClick = {
                                    feedbackAction = FeedbackRepository.ACTION_THUMBS_DOWN
                                    selectedFeedbackReasons = emptySet()
                                },
                                enabled = !feedbackSubmitting
                            ) {
                                Icon(
                                    imageVector = Icons.Default.ThumbDown,
                                    contentDescription = stringResource(R.string.ask_feedback_thumbs_down),
                                    tint = if (feedbackAction == FeedbackRepository.ACTION_THUMBS_DOWN)
                                        MaterialTheme.colorScheme.error
                                    else
                                        MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }

                        val reasonOptions = FeedbackRepository.ragReasonsForAction(feedbackAction)
                        if (reasonOptions.isNotEmpty()) {
                            Spacer(modifier = Modifier.height(8.dp))
                            Row(
                                modifier = Modifier.horizontalScroll(rememberScrollState()),
                                horizontalArrangement = Arrangement.spacedBy(6.dp)
                            ) {
                                reasonOptions.forEach { reason ->
                                    FilterChip(
                                        selected = reason in selectedFeedbackReasons,
                                        onClick = {
                                            selectedFeedbackReasons =
                                                if (reason in selectedFeedbackReasons) {
                                                    selectedFeedbackReasons - reason
                                                } else {
                                                    selectedFeedbackReasons + reason
                                                }
                                        },
                                        label = { Text(reason) },
                                        enabled = !feedbackSubmitting
                                    )
                                }
                            }
                        }

                        Spacer(modifier = Modifier.height(8.dp))
                        OutlinedTextField(
                            value = feedbackComment,
                            onValueChange = { feedbackComment = it.take(300) },
                            label = { Text(stringResource(R.string.ask_feedback_comment_label)) },
                            modifier = Modifier.fillMaxWidth(),
                            maxLines = 3,
                            enabled = !feedbackSubmitting
                        )

                        Spacer(modifier = Modifier.height(8.dp))
                        Button(
                            onClick = {
                                if (feedbackAction.isNullOrBlank()) return@Button
                                scope.launch {
                                    feedbackSubmitting = true
                                    val effectiveRunId = ensureRunIdForFeedback(runId)
                                    runId = effectiveRunId
                                    val result = FeedbackRepository.submit(
                                        targetType = FeedbackRepository.TARGET_RAG_ANSWER,
                                        targetId = effectiveRunId,
                                        action = feedbackAction!!,
                                        reasons = selectedFeedbackReasons.toList(),
                                        comment = feedbackComment.takeIf { it.isNotBlank() },
                                        sourceId = selectedDocumentId,
                                        meta = mapOf(
                                            "run_id" to effectiveRunId,
                                            "query_snapshot" to query.trim().take(500),
                                            "answer_preview" to answer.take(500)
                                        )
                                    )
                                    feedbackSubmitting = false
                                    when (result) {
                                        is FeedbackRepository.Result.Success -> {
                                            snackbarHostState.showSnackbar(feedbackSubmitSuccessMessage)
                                        }
                                        is FeedbackRepository.Result.Error -> {
                                            val detail = result.message.take(200)
                                            snackbarHostState.showSnackbar(
                                                if (detail.isBlank()) feedbackSubmitFailedMessage
                                                else "$feedbackSubmitFailedMessage $detail"
                                            )
                                        }
                                    }
                                }
                            },
                            enabled = !feedbackSubmitting && !feedbackAction.isNullOrBlank()
                        ) {
                            Text(
                                if (feedbackSubmitting) {
                                    stringResource(R.string.ask_feedback_submitting)
                                } else {
                                    stringResource(R.string.ask_feedback_submit)
                                }
                            )
                        }
                    }
                }
            }

        }
    }

    // Document picker bottom sheet
    if (showDocumentPicker) {
        AskDocumentPickerBottomSheet(
            onDismiss = { showDocumentPicker = false },
            onSelect = { id, title ->
                onDocumentSelect(id, title)
                showDocumentPicker = false
            },
            onError = { msg ->
                scope.launch {
                    snackbarHostState.showSnackbar("Error: $msg")
                }
            }
        )
    }
}

@Composable
private fun CitationItemView(
    citation: RagApi.CitationItem,
    onOpenUrl: (String) -> Unit
) {
    val title = citation.title?.takeIf { it.isNotBlank() }
    val url = citation.url?.takeIf { it.isNotBlank() }
    val quotePreview = truncateQuotePreview(citation.quote)

    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .padding(bottom = 8.dp),
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.45f),
        shape = MaterialTheme.shapes.small
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                text = stringResource(
                    R.string.ask_source_item_title,
                    citation.citation_number,
                    title ?: stringResource(R.string.ask_source_untitled)
                ),
                style = MaterialTheme.typography.labelLarge
            )

            if (!quotePreview.isNullOrBlank()) {
                Spacer(modifier = Modifier.height(6.dp))
                Text(
                    text = quotePreview,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            if (!url.isNullOrBlank()) {
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = url,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = stringResource(R.string.ask_open_source_link),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.clickable { onOpenUrl(url) }
                )
            }
        }
    }
}

private fun extractRunId(meta: RagApi.RagMeta?): String? {
    val value = meta?.run_id?.trim()
    if (value.isNullOrBlank() || value == "null") {
        return null
    }
    return value
}

private fun ensureRunIdForFeedback(currentRunId: String?): String {
    val value = currentRunId?.trim()
    if (!value.isNullOrBlank() && value != "null") {
        return value
    }
    return UUID.randomUUID().toString()
}

private fun truncateQuotePreview(rawQuote: String?): String? {
    val quote = rawQuote?.trim()?.takeIf { it.isNotBlank() } ?: return null
    if (quote.length <= MAX_CITATION_QUOTE_PREVIEW_CHARS) {
        return quote
    }
    return quote.take(MAX_CITATION_QUOTE_PREVIEW_CHARS).trimEnd() + "..."
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AskDocumentPickerBottomSheet(
    onDismiss: () -> Unit,
    onSelect: (id: String, title: String?) -> Unit,
    onError: (String) -> Unit
) {
    var documents by remember { mutableStateOf<List<DocumentsApi.DocumentItem>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        scope.launch {
            when (val r = DocumentsRepository.getDocuments(limit = 20, offset = 0, includeSummary = false)) {
                is DocumentsRepository.Result.Success -> documents = r.documents
                is DocumentsRepository.Result.Error -> onError(r.message)
            }
            loading = false
        }
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            Text(
                text = "Select document for RAG",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(bottom = 12.dp)
            )
            if (loading) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(120.dp),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            } else if (documents.isEmpty()) {
                Text(
                    text = "No documents. Add some from the Feed tab.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(vertical = 24.dp)
                )
            } else {
                LazyColumn(
                    modifier = Modifier.heightIn(max = 400.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    items(documents) { doc ->
                        val hasTitle = !doc.title.isNullOrBlank()
                        val displayName = doc.title?.takeIf { it.isNotBlank() }
                            ?: doc.url?.substringAfterLast('/')?.take(50)
                            ?: "Document"
                        Surface(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable {
                                    onSelect(doc.id, displayName)
                                },
                            shape = MaterialTheme.shapes.small,
                            color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                        ) {
                            Column(modifier = Modifier.padding(16.dp)) {
                                Text(
                                    text = displayName,
                                    style = MaterialTheme.typography.bodyMedium
                                )
                                if (!hasTitle && !doc.url.isNullOrBlank()) {
                                    Text(
                                        text = "Title not available",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f)
                                    )
                                }
                            }
                        }
                    }
                }
            }
            Spacer(modifier = Modifier.height(16.dp))
        }
    }
}

@Preview(showBackground = true)
@Composable
fun AskScreenPreview() {
    TekLearningAgentTheme {
        AskScreen(
            selectedDocumentId = null,
            selectedDocumentTitle = null
        )
    }
}
