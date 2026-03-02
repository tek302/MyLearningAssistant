package com.example.learning.agent.data.repository

import android.content.Context
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private const val PREFS_NAME = "feed_refresh_hint"
private const val KEY_REFRESH_FROM_SHARE_AT = "refresh_from_share_at"
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
