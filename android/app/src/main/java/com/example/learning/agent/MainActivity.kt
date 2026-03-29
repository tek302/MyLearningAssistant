package com.example.learning.agent

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.example.learning.agent.data.repository.DocumentsRepository
import com.example.learning.agent.ui.screens.feed.IngestFailureInfo
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.rememberNavController
import com.example.learning.agent.data.repository.IngestRepository
import com.example.learning.agent.data.repository.OnboardingPrefs
import com.example.learning.agent.data.repository.RefreshAndHighlightPrefs
import com.example.learning.agent.ui.components.OnboardingDialog
import com.example.learning.agent.ui.auth.AuthViewModel
import com.example.learning.agent.ui.navigation.*
import com.example.learning.agent.ui.screens.signin.SignInScreen
import com.example.learning.agent.ui.theme.TekLearningAgentTheme
import com.google.firebase.auth.FirebaseAuth
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        val isShareIntent = intent?.action == Intent.ACTION_SEND && intent.type == "text/plain"
        if (isShareIntent) {
            setTheme(com.example.learning.agent.R.style.Theme_TekLearningAgent_Translucent)
        }
        super.onCreate(savedInstanceState)
        if (isShareIntent) {
            window.setBackgroundDrawableResource(android.R.color.transparent)
            // Skip enableEdgeToEdge so we don't introduce a solid background (avoids black flash).
        } else {
            enableEdgeToEdge()
        }
        val shared = consumeSendIntentUrl(intent)
        if (shared != null) {
            runHeadlessIngest(shared.first, shared.second)
            return
        }
        if (isShareIntent) {
            // Had share intent but no URL could be extracted (e.g. user shared plain text).
            Toast.makeText(this, "No link found in shared text", Toast.LENGTH_SHORT).show()
            finish()
            return
        }
        setContent {
            TekLearningAgentTheme {
                RootContent()
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        val shared = consumeSendIntentUrl(intent)
        if (shared != null) {
            runHeadlessIngest(shared.first, shared.second)
        }
    }

    /** Returns (url, title?) if this was a SEND intent with text, and consumes the intent.
     * Many apps (e.g. Chrome) send "Page Title https://url" as EXTRA_TEXT; we extract the URL
     * so the backend does not receive the whole string as the URL (which causes "No connection
     * adapters" when fetching). */
    private fun consumeSendIntentUrl(intent: Intent?): Pair<String, String?>? {
        if (intent?.action != Intent.ACTION_SEND || intent.type != "text/plain") return null
        val raw = intent.getStringExtra(Intent.EXTRA_TEXT)?.trim()?.takeIf { it.isNotEmpty() } ?: return null
        setIntent(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER))
        val (url, title) = extractUrlFromSharedText(raw)
        return url?.let { Pair(it, title) }
    }

    /**
     * Extracts a single URL from shared text. Many share targets send "Title https://example.com"
     * or "Title\nhttps://example.com". Returns (url, title) or (null, null) if no URL found.
     */
    private fun extractUrlFromSharedText(text: String): Pair<String?, String?> {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return null to null
        val urlPattern = Regex("https?://\\S+")
        val match = urlPattern.find(trimmed) ?: return null to null
        val url = match.value
        // If the whole string is just the URL, no title
        if (trimmed == url) return url to null
        val before = trimmed.substring(0, match.range.first).trim()
        val title = before.takeIf { it.isNotEmpty() }
        return url to title
    }

    /**
     * HEADLESS SHARE MODE — keep this behavior when changing code:
     * - Do NOT wait for the network. Show Toast, start ingest in applicationScope, then finish() immediately.
     * - If we waited for ingest to complete (e.g. lifecycleScope.launch { ... finish() }), the activity
     *   would stay visible and the user would see our app (or a black/transparent flash) until the request returns.
     * - By finishing immediately, the user stays in the source app (e.g. Chrome); only the Toast is visible.
     * - Ingest runs in TekLearningAgentApp.applicationScope so it continues after finish(). On success we save
     *   job_id to prefs; the user sees the result when they open the app and go to Feed (polling there).
     * Do not replace with lifecycleScope or add setContent/UI for the Share path.
     */
    private fun runHeadlessIngest(url: String, title: String? = null) {
        if (FirebaseAuth.getInstance().currentUser == null) {
            Toast.makeText(this, "Sign in to add documents", Toast.LENGTH_SHORT).show()
            finish()
            return
        }
        Toast.makeText(applicationContext, "Queued. Open the app and check Feed for the result.", Toast.LENGTH_SHORT).show()
        (application as? TekLearningAgentApp)?.applicationScope?.launch {
            val result = withContext(Dispatchers.IO) { IngestRepository.ingestUrl(url, title) }
            withContext(Dispatchers.Main) {
                when (result) {
                    is IngestRepository.Result.Success -> {
                        RefreshAndHighlightPrefs.setPendingIngestJobIdSync(applicationContext, result.jobId)
                        RefreshAndHighlightPrefs.setRefreshFromShareAtSync(applicationContext)
                    }
                    is IngestRepository.Result.Error ->
                        Toast.makeText(applicationContext, "Error: ${result.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
        finish()
    }
}

@Composable
private fun RootContent() {
    val authViewModel: AuthViewModel = viewModel()
    val authState by authViewModel.authState.collectAsState()

    if (authState.isSignedIn) {
        MainScreen(
            onSignOut = authViewModel::signOut,
            userEmail = authState.userEmail
        )
    } else {
        SignInScreen(viewModel = authViewModel)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(
    onSignOut: () -> Unit = {},
    userEmail: String? = null
) {
    val navController = rememberNavController()
    val currentRoute = getCurrentRoute(navController)
    var selectedDocumentId by remember { mutableStateOf<String?>(null) }
    var selectedDocumentTitle by remember { mutableStateOf<String?>(null) }
    fun ingestFailureSecondaryLine(failCode: String?, errorCode: String?): String = when (failCode?.trim()?.uppercase()) {
        "PDF_TOO_LARGE" -> "Try a smaller file (under the app limit) or split the document."
        "PDF_TOO_LONG" -> "Try fewer pages per upload or split the PDF."
        "PDF_NO_TEXT", "PDF_PARSE_ERROR" -> "Try another PDF with selectable text, or a different export."
        "PDF_PROCESS_ERROR" -> "If this keeps happening, try downloading the PDF and uploading it here."
        "FETCH_TIMEOUT" -> "The download timed out. Retry or upload the file from your device."
        "STORAGE_FETCH_FAILED", "MISSING_STORAGE_PATH" -> "Upload may not have completed. Try uploading the PDF again."
        "URL_INGEST_ERROR", null -> when (errorCode) {
            "fetch_403" -> "This site may block automated access. Try a PDF or another link."
            "fetch_404" -> "Check the URL or try uploading a PDF."
            "timeout" -> "Try again later or upload a PDF."
            else -> "You can try uploading as PDF instead."
        }
        else -> "You can try another link or upload a PDF."
    }

    // Ingest failure queue and dialog at MainScreen so the popup is always visible (any tab, any recomposition).
    var ingestFailureQueue by remember { mutableStateOf<List<IngestFailureInfo>>(emptyList()) }
    var refreshFeedTrigger by remember { mutableStateOf(0) }
    var showOnboarding by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current.applicationContext

    LaunchedEffect(Unit) {
        showOnboarding = OnboardingPrefs.shouldShowOnboarding(context)
    }

    // Determine if bottom nav should be shown (hide on detail screens)
    val showBottomNav = currentRoute in bottomNavItems.map { it.route }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Learning Agent")
                        if (userEmail != null) {
                            Text(userEmail, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                },
                actions = {
                    TextButton(
                        onClick = {
                            OnboardingPrefs.resetOnboardingSync(context)
                            showOnboarding = true
                        }
                    ) {
                        Text("Onboarding")
                    }
                    TextButton(onClick = onSignOut) { Text("Sign out") }
                }
            )
        },
        bottomBar = {
            if (showBottomNav) {
                NavigationBar {
                    bottomNavItems.forEach { destination ->
                        NavigationBarItem(
                            icon = {
                                Icon(
                                    imageVector = destination.icon,
                                    contentDescription = destination.label
                                )
                            },
                            label = { Text(destination.label) },
                            selected = currentRoute == destination.route,
                            onClick = {
                                if (currentRoute != destination.route) {
                                    navController.navigate(destination.route) {
                                        // Pop up to the start destination of the graph to
                                        // avoid building up a large stack of destinations
                                        popUpTo(navController.graph.startDestinationId) {
                                            saveState = true
                                        }
                                        // Avoid multiple copies of the same destination when
                                        // reselecting the same item
                                        launchSingleTop = true
                                        // Restore state when reselecting a previously selected item
                                        restoreState = true
                                    }
                                }
                            }
                        )
                    }
                }
            }
        }
    ) { paddingValues ->
        AppNavHost(
            navController = navController,
            selectedDocumentId = selectedDocumentId,
            selectedDocumentTitle = selectedDocumentTitle,
            onDocumentSelect = { id, title ->
                // Toggle: tap same card again to deselect
                if (id == selectedDocumentId) {
                    selectedDocumentId = null
                    selectedDocumentTitle = null
                } else {
                    selectedDocumentId = id
                    selectedDocumentTitle = title
                }
            },
            onDocumentDeselect = {
                selectedDocumentId = null
                selectedDocumentTitle = null
            },
            onDocumentDeleted = { documentId ->
                if (documentId == selectedDocumentId) {
                    selectedDocumentId = null
                    selectedDocumentTitle = null
                }
            },
            onAskAboutDocument = { id, title ->
                selectedDocumentId = id
                selectedDocumentTitle = title
                navController.navigate(Destination.Ask.route) {
                    popUpTo(navController.graph.startDestinationId) {
                        saveState = true
                    }
                    launchSingleTop = true
                    restoreState = true
                }
            },
            addIngestFailure = { info ->
                if (info.sourceId == null || !ingestFailureQueue.any { it.sourceId == info.sourceId }) {
                    ingestFailureQueue = ingestFailureQueue + info
                }
            },
            refreshFeedTrigger = refreshFeedTrigger,
            onRefreshDone = { refreshFeedTrigger = 0 },
            modifier = Modifier.padding(paddingValues)
        )
    }

    // Ingest failure dialog at root so it always shows (foreground, any tab). OK → delete doc, clear pending job when jobId present, trigger feed refresh.
    if (ingestFailureQueue.isNotEmpty()) {
        val info = ingestFailureQueue.first()
        val context = LocalContext.current.applicationContext
        AlertDialog(
            onDismissRequest = { ingestFailureQueue = ingestFailureQueue.drop(1) },
            title = { Text("Ingest failed") },
            text = {
                Column {
                    Text(info.message)
                    Spacer(modifier = Modifier.height(12.dp))
                    Text(
                        ingestFailureSecondaryLine(info.failCode, info.errorCode),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    scope.launch {
                        info.jobId?.let { jobId ->
                            RefreshAndHighlightPrefs.removePendingIngestJobIdSync(context, jobId)
                        }
                        info.sourceId?.let { id ->
                            when (val r = DocumentsRepository.deleteDocument(id)) {
                                is DocumentsRepository.Result.Success -> {
                                    if (id == selectedDocumentId) {
                                        selectedDocumentId = null
                                        selectedDocumentTitle = null
                                    }
                                }
                                is DocumentsRepository.Result.Error -> { /* could show snackbar from here if we had host state */ }
                            }
                        }
                        refreshFeedTrigger++
                        ingestFailureQueue = ingestFailureQueue.drop(1)
                    }
                }) {
                    Text("OK")
                }
            }
        )
    }

    if (showOnboarding) {
        OnboardingDialog(
            onStart = {
                OnboardingPrefs.markOnboardingCompletedSync(context)
                showOnboarding = false
                navController.navigate(Destination.Feed.route) {
                    popUpTo(navController.graph.startDestinationId) {
                        saveState = true
                    }
                    launchSingleTop = true
                    restoreState = true
                }
            },
            onSkip = {
                OnboardingPrefs.markOnboardingCompletedSync(context)
                showOnboarding = false
            }
        )
    }
}