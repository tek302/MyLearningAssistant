package com.example.learning.agent.ui.screens.notes

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.learning.agent.data.models.Note
import com.example.learning.agent.data.repository.FakeRepository
import com.example.learning.agent.ui.components.NoteCard
import com.example.learning.agent.ui.theme.TekLearningAgentTheme

enum class NoteFilter {
    All, AI, Research, Tagged
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NotesScreen(
    modifier: Modifier = Modifier
) {
    var selectedFilter by remember { mutableStateOf(NoteFilter.All) }
    var showBottomSheet by remember { mutableStateOf(false) }
    val allNotes = FakeRepository.getNotes()
    
    val filteredNotes = remember(selectedFilter, allNotes) {
        when (selectedFilter) {
            NoteFilter.All -> allNotes
            NoteFilter.AI -> allNotes.filter { it.source == "AI" }
            NoteFilter.Research -> allNotes.filter { it.source == "Research" }
            NoteFilter.Tagged -> allNotes.filter { it.tags.isNotEmpty() }
        }
    }

    Scaffold(
        floatingActionButton = {
            FloatingActionButton(
                onClick = { showBottomSheet = true }
            ) {
                Icon(Icons.Default.Add, contentDescription = "Add Note")
            }
        }
    ) { paddingValues ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            // Filter chips
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                FilterChip(
                    selected = selectedFilter == NoteFilter.All,
                    onClick = { selectedFilter = NoteFilter.All },
                    label = { Text("All") }
                )
                FilterChip(
                    selected = selectedFilter == NoteFilter.AI,
                    onClick = { selectedFilter = NoteFilter.AI },
                    label = { Text("AI") }
                )
                FilterChip(
                    selected = selectedFilter == NoteFilter.Research,
                    onClick = { selectedFilter = NoteFilter.Research },
                    label = { Text("Research") }
                )
                FilterChip(
                    selected = selectedFilter == NoteFilter.Tagged,
                    onClick = { selectedFilter = NoteFilter.Tagged },
                    label = { Text("Tagged") }
                )
            }

            // Notes list
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(vertical = 8.dp)
            ) {
                items(filteredNotes.size) { index ->
                    NoteCard(note = filteredNotes[index])
                }
            }
        }
    }

    // Bottom sheet for adding/editing notes
    if (showBottomSheet) {
        NoteBottomSheet(
            onDismiss = { showBottomSheet = false },
            onSave = { title, content, tags ->
                // TODO: Save note
                showBottomSheet = false
            }
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NoteBottomSheet(
    onDismiss: () -> Unit,
    onSave: (String, String, List<String>) -> Unit,
    modifier: Modifier = Modifier
) {
    var title by remember { mutableStateOf("") }
    var content by remember { mutableStateOf("") }
    var tagsText by remember { mutableStateOf("") }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        modifier = modifier
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
        ) {
            Text(
                text = "Add Note",
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.padding(bottom = 16.dp)
            )

            OutlinedTextField(
                value = title,
                onValueChange = { title = it },
                label = { Text("Title") },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 16.dp),
                singleLine = true
            )

            OutlinedTextField(
                value = content,
                onValueChange = { content = it },
                label = { Text("Content") },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 16.dp),
                minLines = 4,
                maxLines = 8
            )

            OutlinedTextField(
                value = tagsText,
                onValueChange = { tagsText = it },
                label = { Text("Tags (comma-separated)") },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 16.dp),
                singleLine = true,
                placeholder = { Text("e.g., AI, Research, Compilers") }
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedButton(
                    onClick = onDismiss,
                    modifier = Modifier.weight(1f)
                ) {
                    Text("Cancel")
                }
                Button(
                    onClick = {
                        val tags = tagsText.split(",")
                            .map { it.trim() }
                            .filter { it.isNotEmpty() }
                        onSave(title, content, tags)
                    },
                    modifier = Modifier.weight(1f)
                ) {
                    Text("Save")
                }
            }

            Spacer(modifier = Modifier.height(16.dp))
        }
    }
}

@Preview(showBackground = true)
@Composable
fun NotesScreenPreview() {
    TekLearningAgentTheme {
        NotesScreen()
    }
}

