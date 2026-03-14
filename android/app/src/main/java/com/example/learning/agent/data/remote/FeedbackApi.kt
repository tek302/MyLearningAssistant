package com.example.learning.agent.data.remote

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.POST

/**
 * Backend feedback API (POST /feedback). Requires Authorization: Bearer <token>.
 */
interface FeedbackApi {

    @POST("feedback")
    suspend fun createFeedback(@Body body: CreateFeedbackRequest): Response<CreateFeedbackResponse>

    data class CreateFeedbackRequest(
        val target_type: String,
        val target_id: String,
        val action: String,
        val reasons: List<String> = emptyList(),
        val comment: String? = null,
        val source_id: String? = null,
        val week_start: String? = null,
        val meta: Map<String, Any?> = emptyMap(),
        val client_event_id: String? = null
    )

    data class CreateFeedbackResponse(
        val id: String,
        val status: String
    )
}

