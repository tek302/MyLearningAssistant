package com.example.learning.agent.ui.screens.ask

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.learning.agent.data.remote.ApiClient
import com.example.learning.agent.data.remote.DocumentsApi
import com.example.learning.agent.data.remote.RagApi
import com.example.learning.agent.data.repository.DocumentsRepository
import com.example.learning.agent.ui.theme.TekLearningAgentTheme
import kotlinx.coroutines.launch

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
    var isLoading by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var showDocumentPicker by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }

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
                        try {
                            val request = RagApi.RagAnswerRequest(
                                query = query.trim(),
                                top_k = 8,
                                document_id = selectedDocumentId,
                                include_citations = false
                            )
                            val response = ApiClient.ragApi.answer(request)
                            if (response.isSuccessful) {
                                val body = response.body()
                                answer = body?.answer ?: ""
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
                            text = "Answer",
                            style = MaterialTheme.typography.titleMedium,
                            modifier = Modifier.padding(bottom = 8.dp)
                        )
                        Text(
                            text = answer,
                            style = MaterialTheme.typography.bodyLarge
                        )
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
