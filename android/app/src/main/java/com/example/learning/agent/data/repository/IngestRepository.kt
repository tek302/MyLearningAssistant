package com.example.learning.agent.data.repository

import android.content.Context
import android.net.Uri
import android.util.Log
import com.example.learning.agent.BuildConfig
import com.example.learning.agent.data.remote.ApiClient
import com.example.learning.agent.data.remote.IngestApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

/**
 * Repository for ingest API. Sends URL to backend; backend inserts into DB and enqueues worker.
 * Can poll GET /ingest/status for job outcome (done/failed).
 */
object IngestRepository {

    private const val TAG = "IngestRepository"

    sealed class Result {
        data class Success(val jobId: String, val status: String) : Result()
        data class Error(val message: String) : Result()
    }

    /** Result of GET /ingest/status. */
    data class StatusResult(
        val state: String,
        val progress: Int,
        val sourceId: String?,
        val error: String?,
        val errorCode: String?,
        /** Same as backend `sources.fail_code` when present. */
        val failCode: String? = null
    )

    sealed class StatusResponse {
        data class Ok(val status: StatusResult) : StatusResponse()
        data class Err(val message: String) : StatusResponse()
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

    suspend fun ingestUrl(url: String, title: String? = null, threadId: String? = null): Result =
        withContext(Dispatchers.IO) {
            val content = url.trim()
            if (content.isEmpty()) {
                return@withContext Result.Error("URL is empty")
            }
            try {
                val type = inferIngestType(content)
                if (BuildConfig.DEBUG) Log.d(TAG, "inferIngestType url=$content type=$type")
                val response = ApiClient.ingestApi.ingest(
                    IngestApi.IngestRequest(type = type, content = content, title = title, threadId = threadId)
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

    /**
     * Upload a local PDF file via POST /ingest/file (multipart).
     * Reads bytes from [uri] using [context]'s ContentResolver.
     * On success returns job_id; same polling flow as [ingestUrl].
     */
    suspend fun ingestPdfFile(uri: Uri, context: Context, title: String? = null, threadId: String? = null): Result =
        withContext(Dispatchers.IO) {
            try {
                val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                    ?: return@withContext Result.Error("Could not read file")
                if (bytes.size > 25 * 1024 * 1024) {
                    return@withContext Result.Error("File too large (max 25MB)")
                }
                val filename = title?.takeIf { it.isNotBlank() }
                    ?: run {
                        val name = uri.lastPathSegment?.substringAfterLast('/')?.takeIf { it.isNotBlank() }
                        name?.takeIf { it.endsWith(".pdf", ignoreCase = true) } ?: "document.pdf"
                    }
                val filePart = MultipartBody.Part.createFormData(
                    "file",
                    filename,
                    bytes.toRequestBody("application/pdf".toMediaTypeOrNull())
                )
                val titlePart = MultipartBody.Part.createFormData(
                    "title",
                    title ?: filename
                )
                val threadPart = threadId?.takeIf { it.isNotBlank() }?.let {
                    MultipartBody.Part.createFormData("thread_id", it)
                }
                val response = ApiClient.ingestApi.ingestFile(filePart, titlePart, threadPart)
                if (response.isSuccessful) {
                    val body = response.body()
                    if (body != null) {
                        Log.d(TAG, "Ingest file success: job_id=${body.job_id} status=${body.status}")
                        Result.Success(body.job_id, body.status)
                    } else {
                        Result.Error("Empty response")
                    }
                } else {
                    val msg = response.errorBody()?.string() ?: "HTTP ${response.code()}"
                    Log.e(TAG, "Ingest file failed: $msg")
                    Result.Error(msg)
                }
            } catch (e: IOException) {
                Log.e(TAG, "Ingest file network error", e)
                Result.Error("Network error: ${e.message}")
            } catch (e: Exception) {
                Log.e(TAG, "Ingest file error", e)
                Result.Error("Error: ${e.message}")
            }
        }

    /**
     * Fetch job status for async ingest. Use after POST /ingest to poll until state is done or failed.
     */
    suspend fun getStatus(jobId: String): StatusResponse = withContext(Dispatchers.IO) {
        try {
            if (BuildConfig.DEBUG) Log.d(TAG, "getStatus request jobId=$jobId")
            val response = ApiClient.ingestApi.getStatus(jobId)
            if (response.isSuccessful) {
                val body = response.body()
                if (body != null) {
                    StatusResponse.Ok(
                        StatusResult(
                            state = body.state,
                            progress = body.progress ?: 0,
                            sourceId = body.sourceId,
                            error = body.error,
                            errorCode = body.errorCode,
                            failCode = body.failCode
                        )
                    )
                } else {
                    StatusResponse.Err("Empty response")
                }
            } else {
                val msg = if (response.code() == 404) {
                    "해당 작업이 이미 삭제되었습니다."
                } else {
                    response.errorBody()?.string() ?: "HTTP ${response.code()}"
                }
                Log.e(TAG, "getStatus failed jobId=$jobId msg=$msg")
                StatusResponse.Err(msg)
            }
        } catch (e: IOException) {
            Log.e(TAG, "getStatus network error", e)
            StatusResponse.Err("Network error: ${e.message}")
        } catch (e: Exception) {
            Log.e(TAG, "getStatus error", e)
            StatusResponse.Err("Error: ${e.message}")
        }
    }
}
