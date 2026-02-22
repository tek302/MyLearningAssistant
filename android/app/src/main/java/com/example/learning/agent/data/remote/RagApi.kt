package com.example.learning.agent.data.remote

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.POST

/**
 * Backend RAG API (POST /rag/answer). Requires Authorization: Bearer <token>.
 */
interface RagApi {

    @POST("rag/answer")
    suspend fun answer(@Body body: RagAnswerRequest): Response<RagAnswerResponse>

    data class RagAnswerRequest(
        val query: String,
        val top_k: Int = 8,
        val document_id: String? = null
    )

    data class RagAnswerResponse(
        val answer: String,
        val citations: List<CitationItem>,
        val meta: Map<String, Any>?
    )

    data class CitationItem(
        val citation_number: Int,
        val chunk_id: String?,
        val source_id: String?,
        val url: String?,
        val title: String?,
        val quote: String?
    )
}
