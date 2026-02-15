package com.example.learning.agent.data.models

data class SummaryCard(
    val id: String,
    val title: String,
    val tldr: String,
    val bullets: List<String>,
    val source: String,
    val readTime: String, // e.g., "3–5 min"
    val fullContent: String
)

