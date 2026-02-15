package com.example.learning.agent.data.models

data class Note(
    val id: String,
    val title: String,
    val content: String,
    val tags: List<String>,
    val createdAt: String,
    val source: String? = null // "AI", "Research", or null
)

