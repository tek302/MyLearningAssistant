package com.example.learning.agent.data.remote

import com.google.gson.annotations.SerializedName
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query

/**
 * Backend S2 API (GET /s2, POST /jobs/s2). Requires Authorization: Bearer <token>.
 */
interface S2Api {

    @GET("s2")
    suspend fun getS2Summaries(
        @Query("week_start") weekStart: String? = null,
        @Query("limit") limit: Int = 20
    ): Response<S2Response>

    @POST("jobs/s2")
    suspend fun enqueueS2Job(@Body body: S2JobRequest): Response<S2JobResponse>

    data class S2Response(
        val summaries: List<S2SummaryItem>
    )

    data class S2SummaryItem(
        val id: String,
        val tldr: String?,
        val bullets: List<String>?,
        val extra: S2Extra?,
        @SerializedName("created_at") val createdAt: String?
    )

    data class S2Extra(
        @SerializedName("week_start") val weekStart: String?,
        @SerializedName("topic_name") val topicName: String?
    )

    data class S2JobRequest(
        @SerializedName("week_start") val weekStart: String? = null
    )

    data class S2JobResponse(
        val job_id: String,
        val status: String
    )
}
