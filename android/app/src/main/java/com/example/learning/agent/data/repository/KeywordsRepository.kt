package com.example.learning.agent.data.repository

import android.util.Log
import com.example.learning.agent.data.remote.ApiClient
import com.example.learning.agent.data.remote.KeywordsApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException

object KeywordsRepository {

    private const val TAG = "KeywordsRepo"
    private val api: KeywordsApi get() = ApiClient.keywordsApi

    /** FastAPI: `{"detail":"..."}` (400) or `{"detail":[{"msg":"..."}]}` (422). */
    private fun parseFastApiError(raw: String?): String {
        if (raw.isNullOrBlank()) return "Request failed"
        return try {
            val obj = JSONObject(raw)
            obj.optJSONArray("detail")?.let { arr ->
                if (arr.length() > 0) {
                    val o = arr.optJSONObject(0)
                    val msg = o?.optString("msg")?.trim().orEmpty()
                    if (msg.isNotEmpty()) return msg
                }
            }
            obj.optString("detail", "").trim().takeIf { it.isNotEmpty() } ?: raw
        } catch (_: Exception) {
            raw
        }
    }

    sealed class Result<out T> {
        data class Success<T>(val data: T) : Result<T>()
        data class Error(val message: String) : Result<Nothing>()
    }

    suspend fun listKeywords(status: String? = null): Result<KeywordsApi.KeywordsListResponse> =
        withContext(Dispatchers.IO) {
            try {
                val response = api.list(status = status)
                if (response.isSuccessful && response.body() != null) {
                    Result.Success(response.body()!!)
                } else {
                    Result.Error(response.errorBody()?.string() ?: "HTTP ${response.code()}")
                }
            } catch (e: IOException) {
                Log.e(TAG, "listKeywords network error", e)
                Result.Error("Network error: ${e.message}")
            } catch (e: Exception) {
                Log.e(TAG, "listKeywords error", e)
                Result.Error("Error: ${e.message}")
            }
        }

    suspend fun createKeyword(keyword: String): Result<KeywordsApi.CreateKeywordResponse> =
        withContext(Dispatchers.IO) {
            try {
                val response = api.create(KeywordsApi.CreateKeywordRequest(keyword))
                if (response.isSuccessful && response.body() != null) {
                    Result.Success(response.body()!!)
                } else {
                    val raw = response.errorBody()?.string() ?: "HTTP ${response.code()}"
                    Result.Error(parseFastApiError(raw))
                }
            } catch (e: IOException) {
                Result.Error("Network error: ${e.message}")
            } catch (e: Exception) {
                Result.Error("Error: ${e.message}")
            }
        }

    suspend fun archiveKeyword(id: String): Result<Boolean> =
        withContext(Dispatchers.IO) {
            try {
                val response = api.delete(id)
                if (response.isSuccessful) Result.Success(true)
                else Result.Error("HTTP ${response.code()}")
            } catch (e: Exception) {
                Result.Error("Error: ${e.message}")
            }
        }

    suspend fun listSuggestions(
        status: String? = null,
        weekStart: String? = null
    ): Result<List<KeywordsApi.SuggestionItem>> =
        withContext(Dispatchers.IO) {
            try {
                val response = api.listSuggestions(status = status, weekStart = weekStart)
                if (response.isSuccessful && response.body() != null) {
                    Result.Success(response.body()!!.items)
                } else {
                    Result.Error(response.errorBody()?.string() ?: "HTTP ${response.code()}")
                }
            } catch (e: IOException) {
                Result.Error("Network error: ${e.message}")
            } catch (e: Exception) {
                Result.Error("Error: ${e.message}")
            }
        }

    suspend fun acceptSuggestion(id: String): Result<KeywordsApi.AcceptResponse> =
        withContext(Dispatchers.IO) {
            try {
                val response = api.acceptSuggestion(id)
                if (response.isSuccessful && response.body() != null) {
                    Result.Success(response.body()!!)
                } else {
                    Result.Error(response.errorBody()?.string() ?: "HTTP ${response.code()}")
                }
            } catch (e: Exception) {
                Result.Error("Error: ${e.message}")
            }
        }

    suspend fun rejectSuggestion(id: String): Result<KeywordsApi.RejectResponse> =
        withContext(Dispatchers.IO) {
            try {
                val response = api.rejectSuggestion(id)
                if (response.isSuccessful && response.body() != null) {
                    Result.Success(response.body()!!)
                } else {
                    Result.Error(response.errorBody()?.string() ?: "HTTP ${response.code()}")
                }
            } catch (e: Exception) {
                Result.Error("Error: ${e.message}")
            }
        }
}
