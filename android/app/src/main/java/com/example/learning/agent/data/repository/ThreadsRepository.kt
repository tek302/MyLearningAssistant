package com.example.learning.agent.data.repository

import android.content.Context
import com.example.learning.agent.data.remote.ApiClient
import com.example.learning.agent.data.remote.ThreadsApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

object ThreadsRepository {

    sealed class Result {
        data class Success(val threads: List<ThreadsApi.InterestThreadItem>) : Result()
        data class Error(val message: String) : Result()
    }

    sealed class CreateResult {
        data class Success(val thread: ThreadsApi.InterestThreadItem) : CreateResult()
        data class Error(val message: String) : CreateResult()
    }

    sealed class ArchiveResult {
        object Success : ArchiveResult()
        data class Error(val message: String) : ArchiveResult()
    }

    /**
     * Load threads and ensure [ThreadPrefs] has a selection (prefers default thread).
     */
    suspend fun refreshSelection(context: Context): Result = withContext(Dispatchers.IO) {
        try {
            val response = ApiClient.threadsApi.listThreads()
            if (!response.isSuccessful) {
                return@withContext Result.Error("HTTP ${response.code()}: ${response.message()}")
            }
            val list = response.body()?.threads ?: emptyList()
            if (list.isNotEmpty()) {
                val current = ThreadPrefs.getSelectedThreadId(context)
                val stillValid = current != null && list.any { it.id == current }
                if (!stillValid) {
                    val def = list.firstOrNull { it.isDefault } ?: list.first()
                    ThreadPrefs.setSelectedThreadId(context, def.id)
                }
            }
            Result.Success(list)
        } catch (e: Exception) {
            Result.Error(e.message ?: "Network error")
        }
    }

    suspend fun createThread(
        context: Context,
        name: String,
        description: String? = null,
        isDefault: Boolean = false,
        selectWhenCreated: Boolean = true
    ): CreateResult = withContext(Dispatchers.IO) {
        val trimmed = name.trim()
        if (trimmed.isBlank()) return@withContext CreateResult.Error("Name is required")
        try {
            val response = ApiClient.threadsApi.createThread(
                ThreadsApi.CreateThreadRequest(
                    name = trimmed,
                    description = description?.trim()?.ifBlank { null },
                    isDefault = isDefault
                )
            )
            if (!response.isSuccessful || response.body() == null) {
                return@withContext CreateResult.Error("HTTP ${response.code()}: ${response.message()}")
            }
            val created = response.body()!!
            if (selectWhenCreated) {
                ThreadPrefs.setSelectedThreadId(context, created.id)
            }
            CreateResult.Success(created)
        } catch (e: Exception) {
            CreateResult.Error(e.message ?: "Network error")
        }
    }

    suspend fun archiveThread(context: Context, threadId: String): ArchiveResult = withContext(Dispatchers.IO) {
        try {
            val response = ApiClient.threadsApi.archiveThread(threadId)
            if (!response.isSuccessful) {
                return@withContext ArchiveResult.Error("HTTP ${response.code()}: ${response.message()}")
            }
            when (val refreshed = refreshSelection(context)) {
                is Result.Success -> {
                    val selected = ThreadPrefs.getSelectedThreadId(context)
                    val stillValid = selected != null && refreshed.threads.any { it.id == selected }
                    if (!stillValid) {
                        val fallback = refreshed.threads.firstOrNull { it.isDefault } ?: refreshed.threads.firstOrNull()
                        ThreadPrefs.setSelectedThreadId(context, fallback?.id)
                    }
                }
                is Result.Error -> {
                    // keep local selection if refresh fails
                }
            }
            ArchiveResult.Success
        } catch (e: Exception) {
            ArchiveResult.Error(e.message ?: "Network error")
        }
    }
}
