package com.example.learning.agent.data.remote

import com.google.gson.annotations.SerializedName
import retrofit2.Response
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * Backend recommendations API (GET /recommendations, DELETE /recommendations/{id}).
 * Requires Authorization: Bearer <token>.
 */
interface RecommendationsApi {

    @GET("recommendations")
    suspend fun list(
        @Query("week_start") weekStart: String? = null,
        @Query("topic_name") topicName: String? = null,
        @Query("limit") limit: Int = 50
    ): Response<ListResponse>

    @DELETE("recommendations/{id}")
    suspend fun delete(@Path("id") id: String): Response<Unit>

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
        @SerializedName("created_at") val createdAt: String?
    )
}
