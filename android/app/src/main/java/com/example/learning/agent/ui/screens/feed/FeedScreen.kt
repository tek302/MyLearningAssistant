package com.example.learning.agent.ui.screens.feed

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.learning.agent.data.remote.DocumentsApi
import com.example.learning.agent.data.repository.DocumentsRepository
import com.example.learning.agent.data.repository.DocumentsCache
import com.example.learning.agent.data.repository.RefreshAndHighlightPrefs
import com.example.learning.agent.data.repository.IngestRepository
import com.example.learning.agent.data.repository.TriggerRepository
import com.example.learning.agent.ui.components.DocumentCard
import com.example.learning.agent.ui.theme.TekLearningAgentTheme
import kotlinx.coroutines.launch

private const val PAGE_SIZE = 5

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FeedScreen(
    selectedDocumentId: String?,
    onDocumentSelect: (id: String, title: String?) -> Unit,
    onCardClick: (String) -> Unit,
    modifier: Modifier = Modifier,
    onDocumentDeselect: () -> Unit = {},
    onDocumentDeleted: (documentId: String) -> Unit = {},
) {
    var documents by remember { mutableStateOf<List<DocumentsApi.DocumentItem>>(emptyList()) }
    var isLoading by remember { mutableStateOf(false) }
    var isRefreshing by remember { mutableStateOf(false) }
    var loadMoreEnabled by remember { mutableStateOf(true) }
    var loadError by remember { mutableStateOf<String?>(null) }
    var urlText by remember { mutableStateOf("") }
    var isIngesting by remember { mutableStateOf(false) }
    var deleteConfirmDocumentId by remember { mutableStateOf<String?>(null) }
    var isDeletingDocument by remember { mutableStateOf(false) }
    var highlightedDocumentIds by remember { mutableStateOf<Set<String>>(emptySet()) }
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }
    val context = LocalContext.current.applicationContext

    suspend fun applyNewDocumentList(newList: List<DocumentsApi.DocumentItem>) {
        val known = RefreshAndHighlightPrefs.getKnownDocumentIds(context)
        val currentIds = newList.map { it.id }.toSet()
        if (known.isEmpty()) {
            RefreshAndHighlightPrefs.setKnownDocumentIds(context, currentIds)
            if (newList.isNotEmpty()) {
                RefreshAndHighlightPrefs.addHighlighted(context, currentIds)
                highlightedDocumentIds = highlightedDocumentIds + currentIds
            } else {
                highlightedDocumentIds = RefreshAndHighlightPrefs.getHighlightedDocumentIds(context)
            }
            return
        }
        val newIds = currentIds - known
        if (newIds.isNotEmpty()) {
            RefreshAndHighlightPrefs.addHighlighted(context, newIds)
            highlightedDocumentIds = highlightedDocumentIds + newIds
        }
        RefreshAndHighlightPrefs.setKnownDocumentIds(context, currentIds)
    }

    fun doDocumentSeen(id: String) {
        scope.launch {
            RefreshAndHighlightPrefs.removeHighlighted(context, id)
            highlightedDocumentIds = highlightedDocumentIds - id
        }
    }

    fun loadPage(offset: Int, append: Boolean) {
        if (isLoading) return
        scope.launch {
            isLoading = true
            loadError = null
            when (val r = DocumentsRepository.getDocuments(limit = PAGE_SIZE, offset = offset, includeSummary = true)) {
                is DocumentsRepository.Result.Success -> {
                    val newList = if (append) documents + r.documents else r.documents
                    documents = newList
                    loadMoreEnabled = r.documents.size >= PAGE_SIZE
                    DocumentsCache.saveCachedDocuments(context, newList)
                    applyNewDocumentList(newList)
                }
                is DocumentsRepository.Result.Error -> {
                    loadError = r.message
                    snackbarHostState.showSnackbar("Error: ${r.message}")
                }
            }
            isLoading = false
        }
    }

    fun doRefresh() {
        if (isRefreshing) return
        scope.launch {
            isRefreshing = true
            loadError = null
            when (val r = DocumentsRepository.getDocuments(limit = PAGE_SIZE, offset = 0, includeSummary = true)) {
                is DocumentsRepository.Result.Success -> {
                    documents = r.documents
                    loadMoreEnabled = r.documents.size >= PAGE_SIZE
                    DocumentsCache.saveCachedDocuments(context, r.documents)
                    applyNewDocumentList(r.documents)
                }
                is DocumentsRepository.Result.Error -> {
                    loadError = r.message
                    snackbarHostState.showSnackbar("Error: ${r.message}")
                }
            }
            isRefreshing = false
        }
    }

    fun doTriggerWorker() {
        scope.launch {
            when (val r = TriggerRepository.triggerWorker()) {
                is TriggerRepository.Result.Success -> {
                    if (r.processed) {
                        snackbarHostState.showSnackbar("Processed job ${r.jobId ?: ""}. Refreshing…")
                        doRefresh()
                    } else {
                        snackbarHostState.showSnackbar("No pending jobs")
                    }
                }
                is TriggerRepository.Result.Error ->
                    snackbarHostState.showSnackbar("Error: ${r.message}")
            }
        }
    }

    fun doDeleteDocument(documentId: String) {
        if (isDeletingDocument) return
        scope.launch {
            isDeletingDocument = true
            when (val r = DocumentsRepository.deleteDocument(documentId)) {
                is DocumentsRepository.Result.Success -> {
                    deleteConfirmDocumentId = null
                    onDocumentDeleted(documentId)
                    snackbarHostState.showSnackbar("Document deleted", withDismissAction = true)
                    doRefresh()
                }
                is DocumentsRepository.Result.Error -> {
                    snackbarHostState.showSnackbar("Error: ${r.message}", withDismissAction = true)
                }
            }
            isDeletingDocument = false
        }
    }

    fun doReprocessDocument(documentId: String) {
        scope.launch {
            snackbarHostState.showSnackbar("Re-processing…")
            when (val r = DocumentsRepository.reprocessDocument(documentId)) {
                is DocumentsRepository.ReprocessResult.Success -> {
                    snackbarHostState.showSnackbar(
                        "Done. Title or summary may have been updated.",
                        withDismissAction = true
                    )
                    doRefresh()
                }
                is DocumentsRepository.ReprocessResult.Error -> {
                    snackbarHostState.showSnackbar("Error: ${r.message}", withDismissAction = true)
                }
            }
        }
    }

    LaunchedEffect(Unit) {
        val shouldRefresh = RefreshAndHighlightPrefs.shouldRefreshFromShare(context)
        highlightedDocumentIds = RefreshAndHighlightPrefs.getHighlightedDocumentIds(context)
        if (shouldRefresh) {
            RefreshAndHighlightPrefs.clearRefreshFromShareAt(context)
            loadPage(0, append = false)
        } else {
            val cached = DocumentsCache.getCachedDocuments(context)
            if (!cached.isNullOrEmpty()) {
                documents = cached
                loadMoreEnabled = cached.size >= PAGE_SIZE
            } else {
                loadPage(0, append = false)
            }
        }
    }

    // Delete confirmation dialog
    if (deleteConfirmDocumentId != null) {
        AlertDialog(
            onDismissRequest = { if (!isDeletingDocument) deleteConfirmDocumentId = null },
            title = { Text("Delete document?") },
            text = { Text("This will remove it from the server. This cannot be undone.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        if (!isDeletingDocument) deleteConfirmDocumentId?.let { doDeleteDocument(it) }
                    },
                    enabled = !isDeletingDocument,
                    colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error)
                ) {
                    if (isDeletingDocument) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(16.dp),
                                strokeWidth = 2.dp
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Deleting…")
                        }
                    } else {
                        Text("Delete")
                    }
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { if (!isDeletingDocument) deleteConfirmDocumentId = null },
                    enabled = !isDeletingDocument
                ) {
                    Text("Cancel")
                }
            }
        )
    }

    Scaffold(snackbarHost = { SnackbarHost(snackbarHostState) }) { paddingValues ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            // URL input + Refresh
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                OutlinedTextField(
                    value = urlText,
                    onValueChange = { urlText = it },
                    label = { Text("Enter URL") },
                    modifier = Modifier.weight(1f),
                    singleLine = true
                )
                Spacer(modifier = Modifier.width(8.dp))
                IconButton(
                    onClick = { doRefresh() },
                    enabled = !isRefreshing
                ) {
                    Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                }
                IconButton(
                    onClick = {
                        val url = urlText.trim()
                        if (url.isEmpty()) return@IconButton
                        isIngesting = true
                        scope.launch {
                            when (val r = IngestRepository.ingestUrl(url)) {
                                is IngestRepository.Result.Success -> {
                                    urlText = ""
                                    snackbarHostState.showSnackbar(
                                        "Queued for ingest. Refreshing list…",
                                        withDismissAction = true
                                    )
                                    loadPage(0, append = false)
                                }
                                is IngestRepository.Result.Error ->
                                    snackbarHostState.showSnackbar("Error: ${r.message}", withDismissAction = true)
                            }
                            isIngesting = false
                        }
                    },
                    enabled = !isIngesting
                ) {
                    if (isIngesting) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(24.dp),
                            strokeWidth = 2.dp
                        )
                    } else {
                        Icon(Icons.AutoMirrored.Filled.Send, contentDescription = "Send URL")
                    }
                }
            }

            // Selected document chip (when one is selected) — tap Deselect to clear
            if (selectedDocumentId != null) {
                val selected = documents.find { it.id == selectedDocumentId }
                if (selected != null) {
                    Surface(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 4.dp),
                        color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.6f),
                        shape = MaterialTheme.shapes.small
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            val name = selected.title?.takeIf { it.isNotBlank() }
                                ?: selected.url?.substringAfterLast('/')?.take(50)
                                ?: "Document"
                            Text(
                                text = "RAG will use: ${name.take(45)}${if (name.length > 45) "…" else ""}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onPrimaryContainer,
                                modifier = Modifier.weight(1f)
                            )
                            TextButton(onClick = onDocumentDeselect) {
                                Text("Deselect", style = MaterialTheme.typography.labelMedium)
                            }
                        }
                    }
                }
            }

            // Document list (or loading / empty / error state)
            when {
                isLoading && documents.isEmpty() -> {
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
                                text = "Loading your documents…",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
                loadError != null && documents.isEmpty() -> {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(24.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                text = "Could not load documents",
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
                            TextButton(onClick = { loadPage(0, append = false) }) {
                                Text("Retry")
                            }
                        }
                    }
                }
                documents.isEmpty() -> {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(24.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                text = "No documents yet",
                                style = MaterialTheme.typography.titleSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(
                                text = "Add a PDF or URL above to ingest. Documents are listed per account.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(modifier = Modifier.height(12.dp))
                            Text(
                                text = "Then tap a card to select it and ask questions in the Ask tab.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.primary
                            )
                        }
                    }
                }
                else -> {
                    PullToRefreshBox(
                        isRefreshing = isRefreshing,
                        onRefresh = { doRefresh() },
                        modifier = Modifier.fillMaxSize()
                    ) {
                        LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(vertical = 8.dp)
                        ) {
                            items(documents) { doc ->
                                DocumentCard(
                                    document = doc,
                                    isSelected = doc.id == selectedDocumentId,
                                    isHighlighted = doc.id in highlightedDocumentIds,
                                    onSelect = {
                                        doDocumentSeen(doc.id)
                                        val displayName = doc.title?.takeIf { it.isNotBlank() }
                                            ?: doc.url?.substringAfterLast('/')?.take(60)
                                            ?: "Document"
                                        onDocumentSelect(doc.id, displayName)
                                    },
                                    onAddNote = { /* TODO */ },
                                    onOpen = {
                                        doDocumentSeen(doc.id)
                                        onCardClick(doc.id)
                                    },
                                    onRefresh = { doRefresh() },
                                    onTriggerWorker = { doTriggerWorker() },
                                    onDelete = { deleteConfirmDocumentId = doc.id },
                                    onReprocess = { doReprocessDocument(doc.id) }
                                )
                            }

                            if (loadMoreEnabled && documents.isNotEmpty()) {
                                item {
                                    Button(
                                        onClick = { loadPage(documents.size, append = true) },
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .padding(16.dp),
                                        enabled = !isLoading
                                    ) {
                                        Text(if (isLoading) "Loading…" else "Load more")
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
fun FeedScreenPreview() {
    TekLearningAgentTheme {
        FeedScreen(
            selectedDocumentId = null,
            onDocumentSelect = { _, _ -> },
            onDocumentDeselect = {},
            onDocumentDeleted = {},
            onCardClick = {}
        )
    }
}
