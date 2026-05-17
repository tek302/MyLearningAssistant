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
        @Query("thread_id") threadId: String? = null,
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
        @SerializedName("topic_name") val topicName: String?,
        @SerializedName("thread_id") val threadId: String? = null,
        @SerializedName("period_start_et") val periodStartEt: String? = null,
        @SerializedName("period_end_et_inclusive") val periodEndEtInclusive: String? = null,
        @SerializedName("period_tz") val periodTz: String? = null,
        // v2 fields — null for legacy/v1 summaries
        val sections: List<S2Section>? = null,
        @SerializedName("emerging_topics") val emergingTopics: List<String>? = null,
        val connections: List<S2Connection>? = null,
        val trajectory: S2Trajectory? = null,
        val reflection: String? = null,
    )

    data class S2Section(
        val keyword: String,
        val insights: List<String>,
        @SerializedName("doc_count") val docCount: Int = 0,
    )

    data class S2Connection(
        val docs: List<String>,
        val insight: String,
    )

    data class S2Trajectory(
        val deepened: List<String>? = null,
        @SerializedName("new_this_week") val newThisWeek: List<String>? = null,
        val paused: List<String>? = null,
    )

    data class S2JobRequest(
        @SerializedName("week_start") val weekStart: String? = null
    )

    data class S2JobResponse(
        val job_id: String,
        val status: String
    )
}
