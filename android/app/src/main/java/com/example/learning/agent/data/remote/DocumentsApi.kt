package com.example.learning.agent.data.remote

import com.google.gson.annotations.SerializedName
import retrofit2.Response
import retrofit2.http.DELETE
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * Backend documents API (GET /documents). Requires Authorization: Bearer <token>.
 */
interface DocumentsApi {

    @GET("documents")
    suspend fun getDocuments(
        @Query("limit") limit: Int = 20,
        @Query("offset") offset: Int = 0,
        @Query("include_summary") include_summary: Boolean = false,
        @Query("thread_id") threadId: String? = null,
        @Query("_t") cacheBust: Long? = null
    ): Response<DocumentsResponse>

    @PATCH("documents/{document_id}")
    suspend fun patchDocument(
        @Path("document_id") documentId: String,
        @Body body: PatchDocumentRequest
    ): Response<PatchDocumentResponse>

    @DELETE("documents/{document_id}")
    suspend fun deleteDocument(@Path("document_id") documentId: String): Response<Unit>

    @POST("documents/{document_id}/reprocess")
    suspend fun reprocessDocument(@Path("document_id") documentId: String): Response<ReprocessResponse>

    data class ReprocessResponse(
        val job_id: String
    )

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
        val thread_id: String? = null,
        val job_id: String? = null,
        val tldr: String? = null,
        val bullets: List<String>? = null
    )

    data class PatchDocumentRequest(
        @SerializedName("thread_id") val threadId: String
    )

    data class PatchDocumentResponse(
        val id: String,
        @SerializedName("thread_id") val threadId: String
    )
}
