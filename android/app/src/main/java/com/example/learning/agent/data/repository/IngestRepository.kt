package com.example.learning.agent.data.repository

import android.net.Uri
import android.util.Log
import com.example.learning.agent.BuildConfig
import com.example.learning.agent.data.remote.ApiClient
import com.example.learning.agent.data.remote.IngestApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException

/**
 * Repository for ingest API. Sends URL to backend; backend inserts into DB and enqueues worker.
 */
object IngestRepository {

    private const val TAG = "IngestRepository"

    sealed class Result {
        data class Success(val jobId: String, val status: String) : Result()
        data class Error(val message: String) : Result()
    }

    /**
     * Infer type: pdf_url if path endsWith ".pdf", path contains "/pdf/", or host is arxiv with /abs/;
     * else url. Backend normalizes arxiv abs -> pdf when type is pdf_url.
     */
    private fun inferIngestType(url: String): String = runCatching {
        val uri = Uri.parse(url) ?: return@runCatching "url"
        val host = uri.host?.lowercase() ?: ""
        val path = uri.path?.lowercase() ?: ""
        val query = uri.query?.lowercase() ?: ""
        when {
            path.endsWith(".pdf") -> "pdf_url"
            "/pdf/" in path -> "pdf_url"
            "format=pdf" in query || "download=pdf" in query -> "pdf_url"
            (host == "arxiv.org" || host == "www.arxiv.org") && path.startsWith("/abs/") -> "pdf_url"
            else -> "url"
        }
    }.getOrElse { "url" }

    suspend fun ingestUrl(url: String, title: String? = null): Result =
        withContext(Dispatchers.IO) {
            val content = url.trim()
            if (content.isEmpty()) {
                return@withContext Result.Error("URL is empty")
            }
            try {
                val type = inferIngestType(content)
                if (BuildConfig.DEBUG) Log.d(TAG, "inferIngestType url=$content type=$type")
                val response = ApiClient.ingestApi.ingest(
                    IngestApi.IngestRequest(type = type, content = content, title = title)
                )
                if (response.isSuccessful) {
                    val body = response.body()
                    if (body != null) {
                        Log.d(TAG, "Ingest success: job_id=${body.job_id} status=${body.status}")
                        Result.Success(body.job_id, body.status)
                    } else {
                        Result.Error("Empty response")
                    }
                } else {
                    val msg = response.errorBody()?.string() ?: "HTTP ${response.code()}"
                    Log.e(TAG, "Ingest failed: $msg")
                    Result.Error(msg)
                }
            } catch (e: IOException) {
                Log.e(TAG, "Ingest network error", e)
                Result.Error("Network error: ${e.message}")
            } catch (e: Exception) {
                Log.e(TAG, "Ingest error", e)
                Result.Error("Error: ${e.message}")
            }
        }
}
