package com.example.learning.agent.data.repository

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private const val PREFS_NAME = "onboarding_prefs"
private const val KEY_ONBOARDING_COMPLETED = "onboarding_completed"
private const val KEY_FIRST_INGEST_COMPLETED_AT = "first_ingest_completed_at"
private const val KEY_FIRST_ASK_COMPLETED_AT = "first_ask_completed_at"

object OnboardingPrefs {

    suspend fun shouldShowOnboarding(context: Context): Boolean = withContext(Dispatchers.IO) {
        !context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getBoolean(KEY_ONBOARDING_COMPLETED, false)
    }

    fun markOnboardingCompletedSync(context: Context) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_ONBOARDING_COMPLETED, true)
            .apply()
    }

    fun resetOnboardingSync(context: Context) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_ONBOARDING_COMPLETED, false)
            .apply()
    }

    fun markFirstIngestCompletedSync(context: Context) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        if (prefs.getLong(KEY_FIRST_INGEST_COMPLETED_AT, 0L) > 0L) return
        prefs.edit()
            .putLong(KEY_FIRST_INGEST_COMPLETED_AT, System.currentTimeMillis())
            .apply()
    }

    fun markFirstAskCompletedSync(context: Context) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        if (prefs.getLong(KEY_FIRST_ASK_COMPLETED_AT, 0L) > 0L) return
        prefs.edit()
            .putLong(KEY_FIRST_ASK_COMPLETED_AT, System.currentTimeMillis())
            .apply()
    }
}
