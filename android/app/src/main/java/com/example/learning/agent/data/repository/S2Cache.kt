package com.example.learning.agent.data.repository

import android.content.Context
import com.example.learning.agent.data.remote.S2Api
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private const val PREFS_NAME = "s2_summaries_cache"
private const val KEY_SUMMARIES_JSON = "s2_summaries_json"
private val gson = Gson()
private val listType = object : TypeToken<List<S2Api.S2SummaryItem>>() {}.type

/**
 * Local cache for S2 (weekly summary) list. Same pattern as DocumentsCache.
 */
object S2Cache {

    suspend fun getCachedSummaries(context: Context): List<S2Api.S2SummaryItem>? =
        withContext(Dispatchers.IO) {
            try {
                val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                val json = prefs.getString(KEY_SUMMARIES_JSON, null) ?: return@withContext null
                gson.fromJson<List<S2Api.S2SummaryItem>>(json, listType)?.takeIf { it.isNotEmpty() }
            } catch (e: Exception) {
                null
            }
        }

    suspend fun saveCachedSummaries(context: Context, summaries: List<S2Api.S2SummaryItem>) =
        withContext(Dispatchers.IO) {
            try {
                val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                prefs.edit()
                    .putString(KEY_SUMMARIES_JSON, gson.toJson(summaries))
                    .apply()
            } catch (_: Exception) { }
        }
}
