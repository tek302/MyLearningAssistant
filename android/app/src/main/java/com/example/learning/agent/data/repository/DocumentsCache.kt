package com.example.learning.agent.data.repository

import android.content.Context
import com.example.learning.agent.data.remote.DocumentsApi
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private const val PREFS_NAME = "documents_cache"
private const val KEY_DOCUMENTS_JSON = "documents_json"
private val gson = Gson()
private val listType = object : TypeToken<List<DocumentsApi.DocumentItem>>() {}.type

/**
 * Local cache for the document list. Uses app-internal storage (no extra permissions).
 * On Feed load, when cache exists we do a quick server check (GET /documents include_summary=false);
 * if first-page ids differ from cache we refresh with include_summary=true.
 */
object DocumentsCache {

    suspend fun getCachedDocuments(context: Context): List<DocumentsApi.DocumentItem>? =
        withContext(Dispatchers.IO) {
            try {
                val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                val json = prefs.getString(KEY_DOCUMENTS_JSON, null) ?: return@withContext null
                gson.fromJson<List<DocumentsApi.DocumentItem>>(json, listType)?.takeIf { it.isNotEmpty() }
            } catch (e: Exception) {
                null
            }
        }

    suspend fun saveCachedDocuments(context: Context, documents: List<DocumentsApi.DocumentItem>) =
        withContext(Dispatchers.IO) {
            try {
                val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                prefs.edit()
                    .putString(KEY_DOCUMENTS_JSON, gson.toJson(documents))
                    .apply()
            } catch (_: Exception) { }
        }
}
