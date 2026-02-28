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

    sealed class ReprocessResult {
        data class Success(val jobId: String) : ReprocessResult()
        data class Error(val message: String) : ReprocessResult()
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

    suspend fun deleteDocument(documentId: String): Result = withContext(Dispatchers.IO) {
        try {
            val response = ApiClient.documentsApi.deleteDocument(documentId)
            if (response.isSuccessful) {
                Result.Success(emptyList())
            } else {
                Result.Error("HTTP ${response.code()}: ${response.message()}")
            }
        } catch (e: Exception) {
            Result.Error(e.message ?: "Network error")
        }
    }

    suspend fun reprocessDocument(documentId: String): ReprocessResult = withContext(Dispatchers.IO) {
        try {
            val response = ApiClient.documentsApi.reprocessDocument(documentId)
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
