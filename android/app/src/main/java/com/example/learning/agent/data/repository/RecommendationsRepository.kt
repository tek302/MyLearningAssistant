package com.example.learning.agent.data.repository

import android.util.Log
import com.example.learning.agent.data.models.Recommendation
import com.example.learning.agent.data.remote.ApiClient
import com.example.learning.agent.data.remote.RecommendationsApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException

/**
 * Repository for recommendations API. List from backend; Process = ingest URL then delete; Remove = delete only.
 */
object RecommendationsRepository {

    private const val TAG = "RecommendationsRepo"
    private val api: RecommendationsApi get() = ApiClient.recommendationsApi

    sealed class ListResult {
        data class Success(val items: List<Recommendation>) : ListResult()
        data class Error(val message: String) : ListResult()
    }

    suspend fun list(
        weekStart: String? = null,
        topicName: String? = null,
        limit: Int = 50
    ): ListResult = withContext(Dispatchers.IO) {
        try {
            val response = api.list(weekStart = weekStart, topicName = topicName, limit = limit)
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) {
                    val items = body.recommendations.map { item ->
                        Recommendation(
                            id = item.id,
                            topicName = item.topicName,
                            weekStart = item.weekStart,
                            title = item.title,
                            abstract = item.abstract,
                            url = item.url,
                            source = item.source,
                            score = item.score,
                            createdAt = item.createdAt
                        )
                    }
                    ListResult.Success(items)
                } else {
                    ListResult.Success(emptyList())
                }
            } else {
                val msg = response.errorBody()?.string() ?: "HTTP ${response.code()}"
                Log.e(TAG, "list failed: $msg")
                ListResult.Error(msg)
            }
        } catch (e: IOException) {
            Log.e(TAG, "list network error", e)
            ListResult.Error("Network error: ${e.message}")
        } catch (e: Exception) {
            Log.e(TAG, "list error", e)
            ListResult.Error("Error: ${e.message}")
        }
    }

    /** Delete one recommendation. Returns true if successful (204). */
    suspend fun delete(id: String): Boolean = withContext(Dispatchers.IO) {
        try {
            val response = api.delete(id)
            if (response.isSuccessful) {
                true
            } else {
                Log.e(TAG, "delete failed: ${response.code()} ${response.errorBody()?.string()}")
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "delete error", e)
            false
        }
    }
}
