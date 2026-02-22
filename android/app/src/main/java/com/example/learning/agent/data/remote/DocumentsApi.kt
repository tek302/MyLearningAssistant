package com.example.learning.agent.data.remote

import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Query

/**
 * Backend documents API (GET /documents). Requires Authorization: Bearer <token>.
 */
interface DocumentsApi {

    @GET("documents")
    suspend fun getDocuments(
        @Query("limit") limit: Int = 20,
        @Query("offset") offset: Int = 0,
        @Query("include_summary") include_summary: Boolean = false
    ): Response<DocumentsResponse>

    data class DocumentsResponse(
        val documents: List<DocumentItem>
    )

    data class DocumentItem(
        val id: String,
        val title: String?,
        val url: String?,
        val source_type: String?,
        val status: String?,
        val pages: Int?,
        val size_mb: Double?,
        val fail_code: String?,
        val created_at: String?,
        val updated_at: String?,
        val tldr: String? = null,
        val bullets: List<String>? = null
    )
}
