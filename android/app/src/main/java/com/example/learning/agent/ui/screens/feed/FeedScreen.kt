package com.example.learning.agent.ui.screens.feed

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.learning.agent.data.repository.DocumentsRepository
import com.example.learning.agent.data.repository.FakeRepository
import com.example.learning.agent.data.repository.IngestRepository
import com.example.learning.agent.ui.components.SummaryCard
import com.example.learning.agent.ui.theme.TekLearningAgentTheme
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FeedScreen(
    onCardClick: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    val feedItems = FakeRepository.getFeedItems()
    var urlText by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }

    Scaffold(snackbarHost = { SnackbarHost(snackbarHostState) }) { paddingValues ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            // Load documents (manual test: GET /documents)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Button(
                    onClick = {
                        scope.launch {
                            when (val r = DocumentsRepository.getDocuments()) {
                                is DocumentsRepository.Result.Success ->
                                    snackbarHostState.showSnackbar("Documents: ${r.count} loaded")
                                is DocumentsRepository.Result.Error ->
                                    snackbarHostState.showSnackbar("Documents error: ${r.message}")
                            }
                        }
                    }
                ) {
                    Text("Load my documents")
                }
            }
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
                                is IngestRepository.Result.Success ->
                                    snackbarHostState.showSnackbar("Sent: $url (job_id=${r.jobId})")
                                is IngestRepository.Result.Error ->
                                    snackbarHostState.showSnackbar("Error: ${r.message}")
                            }
                        }
                    }
                ) {
                    Icon(Icons.Default.Send, contentDescription = "Send URL")
                }
            }

            // Feed items
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(vertical = 8.dp)
            ) {
                items(feedItems.size) { index ->
                    SummaryCard(
                        summary = feedItems[index],
                        onCardClick = { onCardClick(feedItems[index].id) },
                        onSave = { /* TODO */ },
                        onAddNote = { /* TODO */ },
                        onOpen = { /* TODO */ }
                    )
                }
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
fun FeedScreenPreview() {
    TekLearningAgentTheme {
        FeedScreen(onCardClick = {})
    }
}

