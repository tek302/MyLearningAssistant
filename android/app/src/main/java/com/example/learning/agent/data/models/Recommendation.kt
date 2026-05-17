package com.example.learning.agent.data.models

/**
 * Recommendation item from GET /recommendations.
 * Used for card display; Process uses url for ingest, Remove uses id for DELETE.
 */
data class Recommendation(
    val id: String,
    val topicName: String,
    val weekStart: String,
    val title: String,
    val abstract: String?,
    val url: String,
    val source: String,
    val score: Float?,
    val createdAt: String?,
    val threadId: String? = null
) {
    /** Display date; falls back to week_start or empty. */
    val displayDate: String
        get() = createdAt?.take(10) ?: weekStart.take(10).ifEmpty { "" }
}
