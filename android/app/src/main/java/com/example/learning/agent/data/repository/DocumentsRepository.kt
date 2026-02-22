package com.example.learning.agent.data.repository

import com.example.learning.agent.data.remote.ApiClient
import com.example.learning.agent.data.remote.DocumentsApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

object DocumentsRepository {

    sealed class Result {
        data class Success(val documents: List<DocumentsApi.DocumentItem>) : Result()
        data class Error(val message: String) : Result()
    }

    suspend fun getDocuments(
        limit: Int = 20,
        offset: Int = 0,
        includeSummary: Boolean = false
    ): Result = withContext(Dispatchers.IO) {
        try {
            val response = ApiClient.documentsApi.getDocuments(
                limit = limit,
                offset = offset,
                include_summary = includeSummary
            )
            if (response.isSuccessful) {
                val list = response.body()?.documents ?: emptyList()
                Result.Success(list)
            } else {
                Result.Error("HTTP ${response.code()}: ${response.message()}")
            }
        } catch (e: Exception) {
            Result.Error(e.message ?: "Network error")
        }
    }
}
