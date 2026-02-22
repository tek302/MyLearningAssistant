package com.example.learning.agent.ui.screens.feed

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.learning.agent.data.remote.DocumentsApi
import com.example.learning.agent.data.repository.DocumentsRepository
import com.example.learning.agent.data.repository.IngestRepository
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
    modifier: Modifier = Modifier
) {
    var documents by remember { mutableStateOf<List<DocumentsApi.DocumentItem>>(emptyList()) }
    var isLoading by remember { mutableStateOf(false) }
    var loadMoreEnabled by remember { mutableStateOf(true) }
    var loadError by remember { mutableStateOf<String?>(null) }
    var urlText by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }

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
                }
                is DocumentsRepository.Result.Error -> {
                    loadError = r.message
                    snackbarHostState.showSnackbar("Error: ${r.message}")
                }
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) {
        loadPage(0, append = false)
    }

    Scaffold(snackbarHost = { SnackbarHost(snackbarHostState) }) { paddingValues ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            // URL input
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
                    onClick = {
                        val url = urlText.trim()
                        if (url.isEmpty()) return@IconButton
                        scope.launch {
                            when (val r = IngestRepository.ingestUrl(url)) {
                                is IngestRepository.Result.Success -> {
                                    snackbarHostState.showSnackbar("Sent: $url (job_id=${r.jobId})")
                                    loadPage(0, append = false)
                                }
                                is IngestRepository.Result.Error ->
                                    snackbarHostState.showSnackbar("Error: ${r.message}")
                            }
                        }
                    }
                ) {
                    Icon(Icons.Default.Send, contentDescription = "Send URL")
                }
            }

            // Selected document chip (when one is selected)
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
                        Text(
                            text = "Current document: ${selected.title ?: "Untitled"}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onPrimaryContainer,
                            modifier = Modifier.padding(12.dp)
                        )
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
                        }
                    }
                }
                else -> {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = PaddingValues(vertical = 8.dp)
                    ) {
                        items(documents) { doc ->
                            DocumentCard(
                                document = doc,
                                isSelected = doc.id == selectedDocumentId,
                                onSelect = { onDocumentSelect(doc.id, doc.title) },
                                onAddNote = { /* TODO */ },
                                onOpen = { onCardClick(doc.id) }
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

@Preview(showBackground = true)
@Composable
fun FeedScreenPreview() {
    TekLearningAgentTheme {
        FeedScreen(
            selectedDocumentId = null,
            onDocumentSelect = { _, _ -> },
            onCardClick = {}
        )
    }
}
