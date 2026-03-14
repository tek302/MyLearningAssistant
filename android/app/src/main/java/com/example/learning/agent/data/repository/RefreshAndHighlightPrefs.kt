package com.example.learning.agent.data.repository

import android.content.Context
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private const val PREFS_NAME = "feed_refresh_hint"
private const val KEY_REFRESH_FROM_SHARE_AT = "refresh_from_share_at"
private const val KEY_PENDING_INGEST_JOB_ID = "pending_ingest_job_id"
private const val KEY_PENDING_INGEST_JOB_IDS = "pending_ingest_job_ids"
private const val KEY_KNOWN_DOCUMENT_IDS = "known_document_ids"
private const val KEY_HIGHLIGHTED_DOCUMENT_IDS = "highlighted_document_ids"
private const val REFRESH_FROM_SHARE_VALID_MS = 30 * 60 * 1000L // 30 minutes

private val gson = Gson()
private val stringSetType = object : TypeToken<Set<String>>() {}.type

/**
 * Persists "refresh from share" hint and new-document highlight state.
 * - After headless ingest success: set refresh timestamp so next app launch does a network refresh.
 * - After refresh: known ids vs current list → new ids are highlighted until user opens/selects.
 */
object RefreshAndHighlightPrefs {

    suspend fun getRefreshFromShareAt(context: Context): Long = withContext(Dispatchers.IO) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getLong(KEY_REFRESH_FROM_SHARE_AT, 0L)
    }

    suspend fun setRefreshFromShareAt(context: Context) = withContext(Dispatchers.IO) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).edit()
            .putLong(KEY_REFRESH_FROM_SHARE_AT, System.currentTimeMillis())
            .apply()
    }

    suspend fun clearRefreshFromShareAt(context: Context) = withContext(Dispatchers.IO) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).edit()
            .remove(KEY_REFRESH_FROM_SHARE_AT)
            .apply()
    }

    /** Pending ingest job_ids (from Share or Feed Send). Processed one by one; each removed when done/failed/timeout. */
    suspend fun getPendingIngestJobIds(context: Context): List<String> = withContext(Dispatchers.IO) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        var list = prefs.getString(KEY_PENDING_INGEST_JOB_IDS, null)
            ?.split(',')
            ?.map { it.trim() }
            ?.filter { it.isNotEmpty() }
            ?: emptyList()
        if (list.isEmpty()) {
            val legacy = prefs.getString(KEY_PENDING_INGEST_JOB_ID, null)?.trim()?.takeIf { it.isNotEmpty() }
            if (legacy != null) {
                list = listOf(legacy)
                prefs.edit()
                    .putString(KEY_PENDING_INGEST_JOB_IDS, legacy)
                    .remove(KEY_PENDING_INGEST_JOB_ID)
                    .apply()
            }
        }
        list
    }

    fun addPendingIngestJobIdSync(context: Context, jobId: String) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val current = prefs.getString(KEY_PENDING_INGEST_JOB_IDS, null)
            ?.split(',')
            ?.map { it.trim() }
            ?.filter { it.isNotEmpty() }
            ?.distinct()
            ?: emptyList()
        if (jobId in current) return
        val next = (current + jobId).joinToString(",")
        prefs.edit().putString(KEY_PENDING_INGEST_JOB_IDS, next).apply()
    }

    fun removePendingIngestJobIdSync(context: Context, jobId: String) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val current = prefs.getString(KEY_PENDING_INGEST_JOB_IDS, null)
            ?.split(',')
            ?.map { it.trim() }
            ?.filter { it.isNotEmpty() }
            ?: emptyList()
        val next = current.filter { it != jobId }
        if (next.isEmpty()) {
            prefs.edit().remove(KEY_PENDING_INGEST_JOB_IDS).apply()
        } else {
            prefs.edit().putString(KEY_PENDING_INGEST_JOB_IDS, next.joinToString(",")).apply()
        }
    }

    /** First pending job id, if any (for backward compat; prefer getPendingIngestJobIds). */
    suspend fun getPendingIngestJobId(context: Context): String? = withContext(Dispatchers.IO) {
        getPendingIngestJobIds(context).firstOrNull()
    }

    /** Appends job_id to pending list (Share or Feed Send). Replaces previous single-value behavior. */
    fun setPendingIngestJobIdSync(context: Context, jobId: String) {
        addPendingIngestJobIdSync(context, jobId)
    }

    /** Removes all pending ingest job ids. */
    fun clearPendingIngestJobIdSync(context: Context) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).edit()
            .remove(KEY_PENDING_INGEST_JOB_ID)
            .remove(KEY_PENDING_INGEST_JOB_IDS)
            .apply()
    }

    fun setRefreshFromShareAtSync(context: Context) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).edit()
            .putLong(KEY_REFRESH_FROM_SHARE_AT, System.currentTimeMillis())
            .apply()
    }

    suspend fun shouldRefreshFromShare(context: Context): Boolean = withContext(Dispatchers.IO) {
        val at = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getLong(KEY_REFRESH_FROM_SHARE_AT, 0L)
        if (at == 0L) return@withContext false
        System.currentTimeMillis() - at <= REFRESH_FROM_SHARE_VALID_MS
    }

    suspend fun getKnownDocumentIds(context: Context): Set<String> = withContext(Dispatchers.IO) {
        val json = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(KEY_KNOWN_DOCUMENT_IDS, null) ?: return@withContext emptySet()
        (gson.fromJson<Set<String>>(json, stringSetType) ?: emptySet())
    }

    suspend fun setKnownDocumentIds(context: Context, ids: Set<String>) = withContext(Dispatchers.IO) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).edit()
            .putString(KEY_KNOWN_DOCUMENT_IDS, gson.toJson(ids))
            .apply()
    }

    suspend fun getHighlightedDocumentIds(context: Context): Set<String> = withContext(Dispatchers.IO) {
        val json = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(KEY_HIGHLIGHTED_DOCUMENT_IDS, null) ?: return@withContext emptySet()
        (gson.fromJson<Set<String>>(json, stringSetType) ?: emptySet())
    }

    suspend fun addHighlighted(context: Context, ids: Set<String>) = withContext(Dispatchers.IO) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val existing = prefs.getString(KEY_HIGHLIGHTED_DOCUMENT_IDS, null)
            ?.let { gson.fromJson<Set<String>>(it, stringSetType) ?: emptySet() }
            ?: emptySet()
        prefs.edit()
            .putString(KEY_HIGHLIGHTED_DOCUMENT_IDS, gson.toJson(existing + ids))
            .apply()
    }

    suspend fun removeHighlighted(context: Context, id: String) = withContext(Dispatchers.IO) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val existing = prefs.getString(KEY_HIGHLIGHTED_DOCUMENT_IDS, null)
            ?.let { gson.fromJson<Set<String>>(it, stringSetType) ?: emptySet() }
            ?: emptySet()
        prefs.edit()
            .putString(KEY_HIGHLIGHTED_DOCUMENT_IDS, gson.toJson(existing - id))
            .apply()
    }
}
