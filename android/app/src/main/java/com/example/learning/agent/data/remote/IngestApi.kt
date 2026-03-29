package com.example.learning.agent.data.remote

import com.google.gson.annotations.SerializedName
import okhttp3.MultipartBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Query

/**
 * Backend ingest API (POST /ingest, POST /ingest/file, GET /ingest/status).
 * Requires Authorization: Bearer <token> when AUTH_BYPASS_USER_ID is not set.
 */
interface IngestApi {

    @POST("ingest")
    suspend fun ingest(@Body body: IngestRequest): Response<IngestResponse>

    @Multipart
    @POST("ingest/file")
    suspend fun ingestFile(
        @Part file: MultipartBody.Part,
        @Part title: MultipartBody.Part
    ): Response<IngestResponse>

    @GET("ingest/status")
    suspend fun getStatus(@Query("job_id") jobId: String): Response<IngestStatusResponse>

    data class IngestRequest(
        val type: String,  // "url" | "pdf_url" | "text"
        val content: String,
        val title: String? = null
    )

    data class IngestResponse(
        val job_id: String,
        val status: String
    )

    data class IngestStatusResponse(
        val state: String,
        val progress: Int?,
        @SerializedName("source_id") val sourceId: String?,
        val error: String?,
        @SerializedName("error_code") val errorCode: String?,
        /** Backend `sources.fail_code` when the ingest job is tied to a source (e.g. PDF_TOO_LARGE, URL_INGEST_ERROR). */
        @SerializedName("fail_code") val failCode: String? = null
    )
}
