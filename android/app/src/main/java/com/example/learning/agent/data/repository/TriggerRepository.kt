package com.example.learning.agent.data.repository

import com.example.learning.agent.data.remote.ApiClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

object TriggerRepository {

    sealed class Result {
        data class Success(val processed: Boolean, val jobId: String? = null) : Result()
        data class Error(val message: String) : Result()
    }

    suspend fun triggerWorker(): Result = withContext(Dispatchers.IO) {
        try {
            val response = ApiClient.meApi.triggerWorker()
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) {
                    Result.Success(body.processed, body.job_id)
                } else {
                    Result.Success(processed = false)
                }
            } else {
                Result.Error("HTTP ${response.code()}: ${response.message()}")
            }
        } catch (e: Exception) {
            Result.Error(e.message ?: "Network error")
        }
    }
}
