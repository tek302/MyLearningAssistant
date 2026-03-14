package com.example.learning.agent.data.models

import com.example.learning.agent.data.remote.NotesApi

data class Note(
    val id: String,
    val title: String,
    val content: String,
    val tags: List<String>,
    val createdAt: String,
    val source: String? = null, // "AI", "Research", or null (legacy)
    val documentId: String? = null, // source_id from API; null = Free note
    val documentTitle: String? = null // display label for linked document
) {
    val isFreeNote: Boolean get() = documentId == null

    companion object {
        fun fromApi(item: NotesApi.NoteItem): Note = Note(
            id = item.id,
            title = item.topic?.takeIf { it.isNotBlank() } ?: "Untitled",
            content = item.content,
            tags = emptyList(),
            createdAt = item.created_at?.take(10) ?: "", // YYYY-MM-DD for display
            documentId = item.source_id,
            documentTitle = null
        )
    }
}

