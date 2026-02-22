package com.example.learning.agent.ui.screens.ask

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.learning.agent.data.remote.ApiClient
import com.example.learning.agent.data.remote.RagApi
import com.example.learning.agent.ui.theme.TekLearningAgentTheme
import kotlinx.coroutines.launch

@Composable
fun AskScreen(
    selectedDocumentId: String? = null,
    selectedDocumentTitle: String? = null,
    modifier: Modifier = Modifier
) {
    var query by remember { mutableStateOf("") }
    var answer by remember { mutableStateOf("") }
    var citations by remember { mutableStateOf<List<RagApi.CitationItem>>(emptyList()) }
    var isLoading by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }

    Scaffold(snackbarHost = { SnackbarHost(snackbarHostState) }) { paddingValues ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(16.dp)
        ) {
            // Current document banner
            Surface(
                modifier = Modifier.fillMaxWidth(),
                color = if (selectedDocumentId != null)
                    MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.6f)
                else
                    MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f),
                shape = MaterialTheme.shapes.small
            ) {
                Text(
                    text = if (selectedDocumentId != null)
                        "Asking about: ${selectedDocumentTitle ?: "Untitled"}"
                    else
                        "No document selected — answers will use all your documents",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (selectedDocumentId != null)
                        MaterialTheme.colorScheme.onPrimaryContainer
                    else
                        MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(12.dp)
                )
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
                                document_id = selectedDocumentId
                            )
                            val response = ApiClient.ragApi.answer(request)
                            if (response.isSuccessful) {
                                val body = response.body()
                                answer = body?.answer ?: ""
                                citations = body?.citations ?: emptyList()
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

            // Citations
            if (citations.isNotEmpty()) {
                Text(
                    text = "Citations",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(bottom = 8.dp)
                )
                LazyColumn(
                    modifier = Modifier.fillMaxWidth()
                ) {
                    itemsIndexed(citations) { index, citation ->
                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 4.dp),
                            elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(12.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = "[${citation.citation_number}]",
                                    style = MaterialTheme.typography.labelLarge,
                                    color = MaterialTheme.colorScheme.primary,
                                    modifier = Modifier.padding(end = 8.dp)
                                )
                                Text(
                                    text = citation.quote ?: citation.title ?: "",
                                    style = MaterialTheme.typography.bodyMedium
                                )
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
fun AskScreenPreview() {
    TekLearningAgentTheme {
        AskScreen(
            selectedDocumentId = null,
            selectedDocumentTitle = null
        )
    }
}
