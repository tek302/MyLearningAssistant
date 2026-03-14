package com.example.learning.agent

import android.app.Application
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

/**
 * Application-scoped coroutine scope for work that must outlive an Activity.
 * Used by headless Share ingest: MainActivity finishes immediately and runs ingest in this scope
 * so the user does not see our app (no screen switch). Do not remove; keep for Share flow.
 */
class TekLearningAgentApp : Application() {
    val applicationScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
}
