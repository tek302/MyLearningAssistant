package com.example.learning.agent.data.repository

import com.example.learning.agent.data.remote.ApiClient
import com.example.learning.agent.data.remote.S2Api
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

object S2Repository {

    sealed class Result {
        data class Success(val summaries: List<S2Api.S2SummaryItem>) : Result()
        data class Error(val message: String) : Result()
    }

    sealed class ReprocessResult {
        data class Success(val jobId: String) : ReprocessResult()
        data class Error(val message: String) : ReprocessResult()
    }

    suspend fun getS2Summaries(
        weekStart: String? = null,
        threadId: String? = null,
        limit: Int = 20
    ): Result = withContext(Dispatchers.IO) {
        try {
            val response = ApiClient.s2Api.getS2Summaries(weekStart = weekStart, threadId = threadId, limit = limit)
            if (response.isSuccessful) {
                val list = response.body()?.summaries ?: emptyList()
                Result.Success(list)
            } else {
                Result.Error("HTTP ${response.code()}: ${response.message()}")
            }
        } catch (e: Exception) {
            Result.Error(e.message ?: "Network error")
        }
    }

    /** Enqueue S2 job for the given week (re-process). Call triggerWorker after to process it. */
    suspend fun enqueueS2Job(weekStart: String? = null): ReprocessResult = withContext(Dispatchers.IO) {
        try {
            val response = ApiClient.s2Api.enqueueS2Job(S2Api.S2JobRequest(weekStart = weekStart))
            if (response.isSuccessful) {
                val jobId = response.body()?.job_id ?: ""
                ReprocessResult.Success(jobId)
            } else {
                ReprocessResult.Error("HTTP ${response.code()}: ${response.message()}")
            }
        } catch (e: Exception) {
            ReprocessResult.Error(e.message ?: "Network error")
        }
    }
}
