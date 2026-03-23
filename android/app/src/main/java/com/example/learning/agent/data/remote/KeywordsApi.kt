package com.example.learning.agent.data.remote

import com.google.gson.annotations.SerializedName
import retrofit2.Response
import retrofit2.http.*

interface KeywordsApi {

    // ─── Keyword CRUD ───

    @GET("keywords")
    suspend fun list(
        @Query("status") status: String? = null,
        @Query("limit") limit: Int = 100
    ): Response<KeywordsListResponse>

    @POST("keywords")
    suspend fun create(@Body body: CreateKeywordRequest): Response<CreateKeywordResponse>

    @PATCH("keywords/{id}")
    suspend fun update(
        @Path("id") id: String,
        @Body body: UpdateKeywordRequest
    ): Response<UpdateKeywordResponse>

    @DELETE("keywords/{id}")
    suspend fun delete(@Path("id") id: String): Response<Unit>

    // ─── Keyword Suggestions (Stage 1) ───

    @GET("keywords/suggestions")
    suspend fun listSuggestions(
        @Query("status") status: String? = null,
        @Query("week_start") weekStart: String? = null,
        @Query("limit") limit: Int = 20
    ): Response<SuggestionsListResponse>

    @POST("keywords/suggestions/{id}/accept")
    suspend fun acceptSuggestion(@Path("id") id: String): Response<AcceptResponse>

    @POST("keywords/suggestions/{id}/reject")
    suspend fun rejectSuggestion(@Path("id") id: String): Response<RejectResponse>

    // ─── Keyword History ───

    @GET("keywords/history")
    suspend fun history(@Query("limit") limit: Int = 50): Response<HistoryResponse>

    // ─── DTOs ───

    data class KeywordsListResponse(
        val items: List<KeywordItem>,
        @SerializedName("total_active") val totalActive: Int,
        @SerializedName("total_declining") val totalDeclining: Int
    )

    data class KeywordItem(
        val id: String,
        val keyword: String,
        val weight: Float,
        val source: String,
        val status: String,
        @SerializedName("parent_keyword_id") val parentKeywordId: String?,
        @SerializedName("accept_count") val acceptCount: Int?,
        @SerializedName("paper_feedback_up") val paperFeedbackUp: Int?,
        @SerializedName("paper_feedback_down") val paperFeedbackDown: Int?,
        @SerializedName("last_activity") val lastActivity: String?,
        @SerializedName("created_at") val createdAt: String?,
        @SerializedName("updated_at") val updatedAt: String?
    )

    data class CreateKeywordRequest(val keyword: String)
    data class CreateKeywordResponse(val id: String, val keyword: String, val status: String)
    data class UpdateKeywordRequest(val status: String)
    data class UpdateKeywordResponse(val id: String, val updated: Boolean)

    data class SuggestionsListResponse(val items: List<SuggestionItem>)

    data class SuggestionItem(
        val id: String,
        val keyword: String,
        @SerializedName("parent_keyword") val parentKeyword: String?,
        @SerializedName("suggestion_type") val suggestionType: String?,
        val reason: String?,
        val confidence: Float?,
        val status: String,
        @SerializedName("week_start") val weekStart: String?,
        @SerializedName("created_at") val createdAt: String?
    )

    data class AcceptResponse(
        @SerializedName("suggestion_id") val suggestionId: String,
        val status: String,
        @SerializedName("created_keyword_id") val createdKeywordId: String?
    )

    data class RejectResponse(
        @SerializedName("suggestion_id") val suggestionId: String,
        val status: String
    )

    data class HistoryResponse(val events: List<HistoryEvent>)

    data class HistoryEvent(
        val date: String?,
        val type: String,
        val keyword: String,
        @SerializedName("weight_at_time") val weightAtTime: Float?,
        val source: String?,
        val reason: String?
    )
}
