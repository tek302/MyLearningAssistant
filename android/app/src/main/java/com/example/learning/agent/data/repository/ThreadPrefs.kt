package com.example.learning.agent.data.repository

import android.content.Context

private const val PREFS = "thread_prefs"
private const val KEY_SELECTED_THREAD_ID = "selected_thread_id"

/** Persists the user's selected interest thread for scoped lists and ingest. */
object ThreadPrefs {

    fun getSelectedThreadId(context: Context): String? =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_SELECTED_THREAD_ID, null)

    fun setSelectedThreadId(context: Context, threadId: String?) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().apply {
            if (threadId.isNullOrBlank()) remove(KEY_SELECTED_THREAD_ID)
            else putString(KEY_SELECTED_THREAD_ID, threadId)
            apply()
        }
    }
}
