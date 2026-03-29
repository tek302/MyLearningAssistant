package com.example.learning.agent.ui.screens.feed

/**
 * Shown when ingest job fails (from polling or from list). Used by MainScreen dialog so it's visible
 * regardless of which tab is active. OK triggers delete (by sourceId), optional pending job clear (by jobId), and feed refresh.
 */
data class IngestFailureInfo(
    val message: String,
    val errorCode: String?,
    /** Backend `sources.fail_code` when known (mirrors GET /ingest/status). */
    val failCode: String? = null,
    val sourceId: String? = null,
    val jobId: String? = null
)
