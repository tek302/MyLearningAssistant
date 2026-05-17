package com.example.learning.agent.data.remote

import com.google.gson.annotations.SerializedName
import retrofit2.Response
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Path
import retrofit2.http.Query

interface RecommendationsApi {

    @GET("recommendations")
    suspend fun list(
        @Query("week_start") weekStart: String? = null,
        @Query("topic_name") topicName: String? = null,
        @Query("thread_id") threadId: String? = null,
        @Query("limit") limit: Int = 50
    ): Response<ListResponse>

    @DELETE("recommendations/{id}")
    suspend fun delete(@Path("id") id: String): Response<Unit>

    @GET("recommendations/{id}/explanation")
    suspend fun getExplanation(@Path("id") id: String): Response<ExplanationResponse>

    data class ListResponse(
        val recommendations: List<RecommendationItem>
    )

    data class RecommendationItem(
        val id: String,
        @SerializedName("topic_name") val topicName: String,
        @SerializedName("week_start") val weekStart: String,
        val title: String,
        val abstract: String?,
        val url: String,
        val source: String,
        val score: Float?,
        @SerializedName("thread_id") val threadId: String? = null,
        @SerializedName("created_at") val createdAt: String?
    )

    data class ExplanationResponse(
        @SerializedName("recommendation_id") val recommendationId: String,
        @SerializedName("week_start") val weekStart: String?,
        val stage: String?,
        @SerializedName("triggering_keywords") val triggeringKeywords: List<TriggeringKeyword>?,
        @SerializedName("score_breakdown") val scoreBreakdown: ScoreBreakdown?,
        val meta: ExplanationMeta?
    )

    data class TriggeringKeyword(
        val keyword: String,
        val weight: Float?,
        val contribution: String?
    )

    data class ScoreBreakdown(
        @SerializedName("final_score") val finalScore: Float?,
        @SerializedName("keyword_match") val keywordMatch: Float?
    )

    data class ExplanationMeta(
        val source: String?,
        @SerializedName("run_id") val runId: String?,
        @SerializedName("prompt_version") val promptVersion: String?
    )
}
