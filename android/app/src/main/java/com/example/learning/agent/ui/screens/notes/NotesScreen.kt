package com.example.learning.agent.ui.screens.notes

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.learning.agent.data.models.Note
import com.example.learning.agent.data.remote.ApiClient
import com.example.learning.agent.data.remote.DocumentsApi
import com.example.learning.agent.data.remote.NotesApi
import com.example.learning.agent.ui.components.NoteCard
import com.example.learning.agent.ui.theme.TekLearningAgentTheme
import kotlinx.coroutines.launch

sealed class NotesListRow {
    data class Header(val groupKey: String, val title: String, val count: Int) : NotesListRow()
    data class NoteRow(val note: Note) : NotesListRow()
}

enum class NoteFilter {
    All, FreeNotes, ByDocument
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NotesScreen(
    modifier: Modifier = Modifier
) {
    var selectedFilter by remember { mutableStateOf(NoteFilter.All) }
    var showBottomSheet by remember { mutableStateOf(false) }
    var notes by remember { mutableStateOf<List<Note>>(emptyList()) }
    var documentTitleMap by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    val snackbarHostState = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()

    fun loadNotes() {
        scope.launch {
            isLoading = true
            errorMessage = null
            val res = ApiClient.notesApi.getNotes()
            isLoading = false
            if (res.isSuccessful) {
                notes = res.body()?.notes?.map { Note.fromApi(it) } ?: emptyList()
            } else {
                errorMessage = res.message() ?: "Failed to load notes"
                notes = emptyList()
            }
        }
    }

    fun loadDocumentTitles() {
        scope.launch {
            val res = ApiClient.documentsApi.getDocuments(limit = 100, include_summary = false)
            if (res.isSuccessful) {
                val list = res.body()?.documents ?: emptyList()
                documentTitleMap = list.associate { it.id to (it.title?.takeIf { t -> t.isNotBlank() } ?: it.url?.take(50) ?: "Document") }
            }
        }
    }

    LaunchedEffect(Unit) { loadNotes() }
    LaunchedEffect(notes) {
        if (notes.any { it.documentId != null }) loadDocumentTitles()
    }

    val filteredNotes = remember(selectedFilter, notes) {
        when (selectedFilter) {
            NoteFilter.All -> notes
            NoteFilter.FreeNotes -> notes.filter { it.isFreeNote }
            NoteFilter.ByDocument -> notes
        }
    }

    val groupedByDocument = remember(selectedFilter, filteredNotes, documentTitleMap) {
        if (selectedFilter != NoteFilter.ByDocument) return@remember emptyList<Pair<String, List<Note>>>()
        val groups = filteredNotes.groupBy { it.documentId ?: "__free__" }
        groups.map { (key, list) -> key to list.sortedByDescending { it.createdAt } }
            .sortedByDescending { (_, list) -> list.maxOfOrNull { it.createdAt } ?: "" }
    }

    val flatRows = remember(groupedByDocument, selectedFilter) {
        if (selectedFilter != NoteFilter.ByDocument) emptyList<NotesListRow>()
        else groupedByDocument.flatMap { (key, list) ->
            listOf(NotesListRow.Header(key, when (key) {
                "__free__" -> "Free notes"
                else -> documentTitleMap[key] ?: "Document"
            }, list.size)) + list.map { NotesListRow.NoteRow(it) }
        }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
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
                    selected = selectedFilter == NoteFilter.FreeNotes,
                    onClick = { selectedFilter = NoteFilter.FreeNotes },
                    label = { Text("Free notes") }
                )
                FilterChip(
                    selected = selectedFilter == NoteFilter.ByDocument,
                    onClick = { selectedFilter = NoteFilter.ByDocument },
                    label = { Text("By document") }
                )
            }

            if (errorMessage != null) {
                Text(
                    text = errorMessage!!,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(16.dp)
                )
            }

            when {
                isLoading -> Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
                selectedFilter == NoteFilter.ByDocument -> LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(vertical = 8.dp)
                ) {
                    items(flatRows.size, key = { index ->
                        when (val row = flatRows[index]) {
                            is NotesListRow.Header -> "h_${row.groupKey}"
                            is NotesListRow.NoteRow -> row.note.id
                        }
                    }) { index ->
                        when (val row = flatRows[index]) {
                            is NotesListRow.Header -> Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(horizontal = 16.dp, vertical = 8.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = "${row.title} (${row.count})",
                                    style = MaterialTheme.typography.titleSmall,
                                    color = MaterialTheme.colorScheme.primary
                                )
                                if (row.groupKey != "__free__") {
                                    TextButton(
                                        onClick = {
                                            scope.launch {
                                                val res = ApiClient.documentsApi.deleteDocument(row.groupKey)
                                                if (res.isSuccessful) {
                                                    loadNotes()
                                                    snackbarHostState.showSnackbar("Document deleted", withDismissAction = true)
                                                } else {
                                                    snackbarHostState.showSnackbar("Failed to delete document", withDismissAction = true)
                                                }
                                            }
                                        }
                                    ) {
                                        Text("Delete document", color = MaterialTheme.colorScheme.error)
                                    }
                                }
                            }
                            is NotesListRow.NoteRow -> NoteCard(
                                note = row.note,
                                onDelete = {
                                    val toRemove = row.note
                                    notes = notes.filter { it.id != toRemove.id }
                                    scope.launch {
                                        val res = ApiClient.notesApi.deleteNote(toRemove.id)
                                        if (!res.isSuccessful) {
                                            notes = listOf(toRemove) + notes.filter { it.id != toRemove.id }
                                            snackbarHostState.showSnackbar("Failed to delete note", withDismissAction = true)
                                        }
                                    }
                                }
                            )
                        }
                    }
                }
                else -> LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(vertical = 8.dp)
                ) {
                    items(filteredNotes, key = { it.id }) { note ->
                        NoteCard(
                            note = note,
                            onDelete = {
                                val toRemove = note
                                notes = notes.filter { it.id != toRemove.id }
                                scope.launch {
                                    val res = ApiClient.notesApi.deleteNote(toRemove.id)
                                    if (!res.isSuccessful) {
                                        notes = listOf(toRemove) + notes.filter { it.id != toRemove.id }
                                        snackbarHostState.showSnackbar("Failed to delete note", withDismissAction = true)
                                    }
                                }
                            }
                        )
                    }
                }
            }
        }
    }

    if (showBottomSheet) {
        NoteBottomSheet(
            onDismiss = { showBottomSheet = false },
            onSave = { title, content, sourceId ->
                val topic = title.takeIf { it.isNotBlank() }
                val body = NotesApi.CreateNoteRequest(
                    content = content,
                    source_id = sourceId,
                    topic = topic
                )
                val pendingId = "pending-${System.currentTimeMillis()}"
                val optimisticNote = Note(
                    id = pendingId,
                    title = topic ?: "Untitled",
                    content = content,
                    tags = emptyList(),
                    createdAt = "",
                    documentId = null,
                    documentTitle = null
                )
                showBottomSheet = false
                notes = listOf(optimisticNote) + notes
                scope.launch {
                    val res = ApiClient.notesApi.createNote(body)
                    if (res.isSuccessful) {
                        val created = res.body()
                        if (created != null) {
                            notes = listOf(Note.fromApi(created)) + notes.filter { it.id != pendingId }
                        } else {
                            loadNotes()
                        }
                        snackbarHostState.showSnackbar("Note saved", withDismissAction = true)
                    } else {
                        notes = notes.filter { it.id != pendingId }
                        snackbarHostState.showSnackbar(
                            "Failed to save: ${res.message()}",
                            withDismissAction = true
                        )
                    }
                }
            }
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NoteBottomSheet(
    onDismiss: () -> Unit,
    onSave: (title: String, content: String, sourceId: String?) -> Unit,
    documentId: String? = null,
    documentTitle: String? = null,
    modifier: Modifier = Modifier
) {
    var title by remember { mutableStateOf("") }
    var content by remember { mutableStateOf("") }
    var tagsText by remember { mutableStateOf("") }

    val sheetTitle = if (documentTitle != null) "Add note to: $documentTitle" else "Add Note"

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
                text = sheetTitle,
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
                        onSave(title, content, documentId)
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

