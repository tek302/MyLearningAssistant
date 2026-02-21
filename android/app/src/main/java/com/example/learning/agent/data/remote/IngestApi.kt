package com.example.learning.agent.data.remote

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.Header
import retrofit2.http.POST

/**
 * Backend ingest API (POST /ingest).
 * Requires Authorization: Bearer <token> when AUTH_BYPASS_USER_ID is not set.
 */
interface IngestApi {

    @POST("ingest")
    suspend fun ingest(@Body body: IngestRequest): Response<IngestResponse>

    data class IngestRequest(
        val type: String,  // "url" | "pdf_url" | "text"
        val content: String,
        val title: String? = null
    )

    data class IngestResponse(
        val job_id: String,
        val status: String
    )
}
