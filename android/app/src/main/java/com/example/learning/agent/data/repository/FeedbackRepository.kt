package com.example.learning.agent.data.repository

import android.util.Log
import com.example.learning.agent.data.remote.ApiClient
import com.example.learning.agent.data.remote.FeedbackApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException
import java.util.UUID

object FeedbackRepository {

    private const val TAG = "FeedbackRepository"

    const val TARGET_RECOMMENDATION = "recommendation"
    const val TARGET_SUMMARY_S2 = "summary_s2"
    const val TARGET_RAG_ANSWER = "rag_answer"

    const val ACTION_THUMBS_UP = "thumbs_up"
    const val ACTION_THUMBS_DOWN = "thumbs_down"
    const val ACTION_PROCESS = "process"
    const val ACTION_REMOVE = "remove"

    val RECOMMENDATION_REASONS = listOf(
        "want_more_like_this",
        "not_relevant",
        "too_basic",
        "too_advanced",
    )

    val SUMMARY_S2_REASONS = listOf(
        "helpful",
        "too_generic",
        "too_long",
        "wrong_focus",
    )

    val RAG_POSITIVE_REASONS = listOf(
        "good_answer"
    )

    val RAG_NEGATIVE_REASONS = listOf(
        "not_relevant",
        "hallucination_suspected",
        "too_shallow",
    )

    fun ragReasonsForAction(action: String?): List<String> {
        return when (action) {
            ACTION_THUMBS_UP -> RAG_POSITIVE_REASONS
            ACTION_THUMBS_DOWN -> RAG_NEGATIVE_REASONS
            else -> emptyList()
        }
    }

    sealed class Result {
        data class Success(val id: String) : Result()
        data class Error(val message: String) : Result()
    }

    suspend fun submit(
        targetType: String,
        targetId: String,
        action: String,
        reasons: List<String> = emptyList(),
        comment: String? = null,
        sourceId: String? = null,
        weekStart: String? = null,
        meta: Map<String, Any?> = emptyMap(),
    ): Result = withContext(Dispatchers.IO) {
        try {
            val response = ApiClient.feedbackApi.createFeedback(
                FeedbackApi.CreateFeedbackRequest(
                    target_type = targetType,
                    target_id = targetId,
                    action = action,
                    reasons = reasons,
                    comment = comment?.trim()?.takeIf { it.isNotEmpty() },
                    source_id = sourceId,
                    week_start = weekStart,
                    meta = meta,
                    client_event_id = "android-${UUID.randomUUID()}"
                )
            )
            if (response.isSuccessful) {
                val id = response.body()?.id ?: ""
                Result.Success(id)
            } else {
                val msg = response.errorBody()?.string() ?: "HTTP ${response.code()}"
                Log.e(TAG, "submit failed: $msg")
                Result.Error(msg)
            }
        } catch (e: IOException) {
            Log.e(TAG, "submit network error", e)
            Result.Error("Network error: ${e.message}")
        } catch (e: Exception) {
            Log.e(TAG, "submit error", e)
            Result.Error("Error: ${e.message}")
        }
    }
}

