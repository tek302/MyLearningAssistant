package com.example.learning.agent.ui.screens.feed

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Upload
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import android.util.Log
import android.net.Uri
import com.example.learning.agent.BuildConfig
import com.example.learning.agent.data.remote.DocumentsApi
import com.example.learning.agent.data.repository.DocumentsRepository
import com.example.learning.agent.data.repository.DocumentsCache
import com.example.learning.agent.data.repository.RefreshAndHighlightPrefs
import com.example.learning.agent.data.repository.IngestRepository
import com.example.learning.agent.data.repository.OnboardingPrefs
import com.example.learning.agent.data.repository.TriggerRepository
import com.example.learning.agent.data.remote.ApiClient
import com.example.learning.agent.data.remote.NotesApi
import com.example.learning.agent.ui.components.DocumentCard
import com.example.learning.agent.ui.screens.notes.NoteBottomSheet
import com.example.learning.agent.ui.theme.TekLearningAgentTheme
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.TimeoutCancellationException

private const val PAGE_SIZE = 5
// Fast initial polling so user sees fail/success sooner; then back off to limit server load.
private const val INGEST_POLL_INTERVAL_FAST_MS = 1000L   // first N polls (quick 403/404 often surface in ~1–3s)
private const val INGEST_POLL_FAST_COUNT = 12
private const val INGEST_POLL_INTERVAL_MS = 2500L
private const val INGEST_POLL_MAX_COUNT = 48
private const val INGEST_POLL_TIMEOUT_MS = INGEST_POLL_FAST_COUNT * INGEST_POLL_INTERVAL_FAST_MS + (INGEST_POLL_MAX_COUNT - INGEST_POLL_FAST_COUNT) * INGEST_POLL_INTERVAL_MS + 10_000L // hard cap

private const val TAG_FEED_INGEST = "FeedIngest"

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FeedScreen(
    selectedDocumentId: String?,
    onDocumentSelect: (id: String, title: String?) -> Unit,
    onCardClick: (String) -> Unit,
    modifier: Modifier = Modifier,
    onDocumentDeselect: () -> Unit = {},
    onDocumentDeleted: (documentId: String) -> Unit = {},
    addIngestFailure: (IngestFailureInfo) -> Unit = {},
    refreshFeedTrigger: Int = 0,
    onRefreshDone: () -> Unit = {},
) {
    var documents by remember { mutableStateOf<List<DocumentsApi.DocumentItem>>(emptyList()) }
    var isLoading by remember { mutableStateOf(false) }
    var isRefreshing by remember { mutableStateOf(false) }
    var loadMoreEnabled by remember { mutableStateOf(true) }
    var loadError by remember { mutableStateOf<String?>(null) }
    var urlText by remember { mutableStateOf("") }
    var isIngesting by remember { mutableStateOf(false) }
    var lastIngestJobId by remember { mutableStateOf<String?>(null) }
    // When set, clear lastIngestJobId in a separate effect so the polling LaunchedEffect is not cancelled
    // before queue/state updates are applied (fixes error popup not showing when app is in foreground, and 2nd popup).
    var pendingClearPollingJobId by remember { mutableStateOf<String?>(null) }
    var deleteConfirmDocumentId by remember { mutableStateOf<String?>(null) }
    var isDeletingDocument by remember { mutableStateOf(false) }
    var addNoteForDocument by remember { mutableStateOf<DocumentsApi.DocumentItem?>(null) }
    var highlightedDocumentIds by remember { mutableStateOf<Set<String>>(emptySet()) }
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }
    val context = LocalContext.current.applicationContext

    val pdfPickerLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        uri ?: return@rememberLauncherForActivityResult
        isIngesting = true
        scope.launch {
            when (val r = IngestRepository.ingestPdfFile(uri, context)) {
                is IngestRepository.Result.Success -> {
                    RefreshAndHighlightPrefs.setPendingIngestJobIdSync(context, r.jobId)
                    lastIngestJobId = r.jobId
                    snackbarHostState.showSnackbar(
                        "Queued. Checking result…",
                        withDismissAction = true
                    )
                }
                is IngestRepository.Result.Error ->
                    snackbarHostState.showSnackbar("Error: ${r.message}", withDismissAction = true)
            }
            isIngesting = false
        }
    }

    suspend fun applyNewDocumentList(newList: List<DocumentsApi.DocumentItem>) {
        val known = RefreshAndHighlightPrefs.getKnownDocumentIds(context)
        val currentIds = newList.map { it.id }.toSet()
        if (known.isEmpty()) {
            RefreshAndHighlightPrefs.setKnownDocumentIds(context, currentIds)
            if (newList.isNotEmpty()) {
                RefreshAndHighlightPrefs.addHighlighted(context, currentIds)
                highlightedDocumentIds = highlightedDocumentIds + currentIds
            } else {
                highlightedDocumentIds = RefreshAndHighlightPrefs.getHighlightedDocumentIds(context)
            }
            return
        }
        val newIds = currentIds - known
        if (newIds.isNotEmpty()) {
            RefreshAndHighlightPrefs.addHighlighted(context, newIds)
            highlightedDocumentIds = highlightedDocumentIds + newIds
        }
        // Merge with existing known so we never "forget" IDs seen in a previous load-more
        // (e.g. after restart we may load only first page; without merge, load-more would re-highlight those cards)
        RefreshAndHighlightPrefs.setKnownDocumentIds(context, known + currentIds)
    }

    /**
     * Prefer stable backend [failCode] (sources.fail_code), then derived [errorCode] from job error text,
     * then first line of [fullError].
     */
    fun shortIngestFailureMessage(failCode: String?, errorCode: String?, fullError: String?): String {
        when (failCode?.trim()?.uppercase()) {
            "FETCH_TIMEOUT" -> return "Download timed out. Try again or use a smaller file."
            "PDF_TOO_LARGE" -> return "PDF exceeds size limit on the server."
            "PDF_TOO_LONG" -> return "PDF has too many pages for the server limit."
            "PDF_NO_TEXT" -> return "No extractable text in this PDF (e.g. scanned image). Try another file."
            "PDF_PARSE_ERROR" -> return "Could not read this PDF."
            "PDF_PROCESS_ERROR" -> {
                val line = fullError?.lineSequence()?.firstOrNull()?.take(120)?.trim()
                return line?.takeIf { it.isNotEmpty() } ?: "PDF processing failed."
            }
            "STORAGE_FETCH_FAILED" -> return "Could not load the uploaded file. Try uploading again."
            "MISSING_STORAGE_PATH" -> return "Upload storage misconfiguration."
            "USER_MISMATCH" -> return "Permission error for this document."
            "TEXT_NOT_SUPPORTED" -> return "This text ingest type is not supported."
            "UNKNOWN_SOURCE_TYPE" -> return "Unsupported document type."
            "URL_INGEST_ERROR" -> {
                val line = fullError?.lineSequence()?.firstOrNull()?.take(120)?.trim()
                return line?.takeIf { it.isNotEmpty() }
                    ?: "Could not fetch or extract content from this URL."
            }
            null, "" -> { /* fall through */ }
            else -> {
                val line = fullError?.lineSequence()?.firstOrNull()?.take(120)?.trim()
                return line?.takeIf { it.isNotEmpty() } ?: "Ingest failed (${failCode})."
            }
        }
        return when (errorCode) {
            "fetch_403" -> "Access denied (403). Some sites block server requests."
            "fetch_404" -> "Page not found (404)."
            "timeout" -> "Request timed out."
            else -> fullError?.lineSequence()?.firstOrNull()?.take(120) ?: "Something went wrong."
        }
    }

    // When document list is loaded from API (or cache), push any failed docs into the failure queue
    // so the user sees the popup even when the failure was never detected by polling (e.g. first open after share, or refresh-only).
    fun notifyFailedDocumentsFromList(list: List<DocumentsApi.DocumentItem>) {
        for (doc in list) {
            if ((doc.status?.lowercase() ?: "") != "failed") continue
            addIngestFailure(
                IngestFailureInfo(
                    message = shortIngestFailureMessage(doc.fail_code, null, null),
                    errorCode = null,
                    failCode = doc.fail_code,
                    sourceId = doc.id,
                    jobId = doc.job_id
                )
            )
        }
    }

    fun doDocumentSeen(id: String) {
        scope.launch {
            RefreshAndHighlightPrefs.removeHighlighted(context, id)
            highlightedDocumentIds = highlightedDocumentIds - id
        }
    }

    fun loadPage(offset: Int, append: Boolean) {
        if (isLoading) return
        scope.launch {
            isLoading = true
            loadError = null
            when (val r = DocumentsRepository.getDocuments(limit = PAGE_SIZE, offset = offset, includeSummary = true)) {
                is DocumentsRepository.Result.Success -> {
                    val newList = if (append) documents + r.documents else r.documents
                    documents = newList
                    loadMoreEnabled = r.documents.size >= PAGE_SIZE
                    DocumentsCache.saveCachedDocuments(context, newList)
                    applyNewDocumentList(newList)
                    notifyFailedDocumentsFromList(newList)
                }
                is DocumentsRepository.Result.Error -> {
                    loadError = r.message
                    snackbarHostState.showSnackbar("Error: ${r.message}")
                }
            }
            isLoading = false
        }
    }

    fun doRefresh(onDone: (() -> Unit)? = null) {
        if (isRefreshing) return
        scope.launch {
            isRefreshing = true
            loadError = null
            when (val r = DocumentsRepository.getDocuments(limit = PAGE_SIZE, offset = 0, includeSummary = true)) {
                is DocumentsRepository.Result.Success -> {
                    documents = r.documents
                    loadMoreEnabled = r.documents.size >= PAGE_SIZE
                    DocumentsCache.saveCachedDocuments(context, r.documents)
                    applyNewDocumentList(r.documents)
                    notifyFailedDocumentsFromList(r.documents)
                }
                is DocumentsRepository.Result.Error -> {
                    loadError = r.message
                    snackbarHostState.showSnackbar("Error: ${r.message}")
                }
            }
            isRefreshing = false
            onDone?.invoke()
        }
    }

    fun doTriggerWorker() {
        scope.launch {
            when (val r = TriggerRepository.triggerWorker()) {
                is TriggerRepository.Result.Success -> {
                    if (r.processed) {
                        snackbarHostState.showSnackbar("Processed job ${r.jobId ?: ""}. Refreshing…")
                        doRefresh()
                    } else {
                        snackbarHostState.showSnackbar("No pending jobs")
                    }
                }
                is TriggerRepository.Result.Error ->
                    snackbarHostState.showSnackbar("Error: ${r.message}")
            }
        }
    }

    fun doDeleteDocument(documentId: String) {
        if (isDeletingDocument) return
        scope.launch {
            isDeletingDocument = true
            when (val r = DocumentsRepository.deleteDocument(documentId)) {
                is DocumentsRepository.Result.Success -> {
                    deleteConfirmDocumentId = null
                    onDocumentDeleted(documentId)
                    snackbarHostState.showSnackbar("Document deleted", withDismissAction = true)
                    doRefresh()
                }
                is DocumentsRepository.Result.Error -> {
                    snackbarHostState.showSnackbar("Error: ${r.message}", withDismissAction = true)
                }
            }
            isDeletingDocument = false
        }
    }

    fun doReprocessDocument(documentId: String) {
        scope.launch {
            snackbarHostState.showSnackbar("Re-processing…")
            when (val r = DocumentsRepository.reprocessDocument(documentId)) {
                is DocumentsRepository.ReprocessResult.Success -> {
                    snackbarHostState.showSnackbar(
                        "Done. Title or summary may have been updated.",
                        withDismissAction = true
                    )
                    doRefresh()
                }
                is DocumentsRepository.ReprocessResult.Error -> {
                    snackbarHostState.showSnackbar("Error: ${r.message}", withDismissAction = true)
                }
            }
        }
    }

    LaunchedEffect(Unit) {
        val shouldRefresh = RefreshAndHighlightPrefs.shouldRefreshFromShare(context)
        highlightedDocumentIds = RefreshAndHighlightPrefs.getHighlightedDocumentIds(context)
        if (shouldRefresh) {
            RefreshAndHighlightPrefs.clearRefreshFromShareAt(context)
            loadPage(0, append = false)
        } else {
            val cached = DocumentsCache.getCachedDocuments(context)
            if (!cached.isNullOrEmpty()) {
                documents = cached
                loadMoreEnabled = cached.size >= PAGE_SIZE
                notifyFailedDocumentsFromList(cached)
                // Quick sync check: compare server first-page ids with cache; if different, refresh feed (BE 수정 없이 include_summary=false 활용).
                when (val r = DocumentsRepository.getDocuments(limit = PAGE_SIZE, offset = 0, includeSummary = false)) {
                    is DocumentsRepository.Result.Success -> {
                        val serverIds = r.documents.map { it.id }.toSet()
                        val cachedFirstIds = cached.take(PAGE_SIZE).map { it.id }.toSet()
                        if (serverIds != cachedFirstIds) {
                            when (val r2 = DocumentsRepository.getDocuments(limit = PAGE_SIZE, offset = 0, includeSummary = true)) {
                                is DocumentsRepository.Result.Success -> {
                                    documents = r2.documents
                                    loadMoreEnabled = r2.documents.size >= PAGE_SIZE
                                    DocumentsCache.saveCachedDocuments(context, r2.documents)
                                    applyNewDocumentList(r2.documents)
                                    notifyFailedDocumentsFromList(r2.documents)
                                }
                                is DocumentsRepository.Result.Error -> {
                                    loadError = r2.message
                                    snackbarHostState.showSnackbar("Error: ${r2.message}")
                                }
                            }
                        }
                    }
                    is DocumentsRepository.Result.Error -> { /* keep cache on light-check failure */ }
                }
            } else {
                loadPage(0, append = false)
            }
        }
        // Restore pending ingest from Share (or previous Feed Send) so we poll and show result even if user left Feed
        val pendingIds = RefreshAndHighlightPrefs.getPendingIngestJobIds(context)
        if (pendingIds.isNotEmpty()) lastIngestJobId = pendingIds.first()
        if (BuildConfig.DEBUG && pendingIds.isNotEmpty()) {
            Log.d(TAG_FEED_INGEST, "restored pending=${pendingIds.size} ids=${pendingIds.take(3).joinToString(",")}${if (pendingIds.size > 3) "..." else ""}, lastIngestJobId=${pendingIds.first()}")
        }
    }

    // When MainScreen requests feed refresh (e.g. after ingest failure OK → delete), run doRefresh and signal done.
    LaunchedEffect(refreshFeedTrigger) {
        if (refreshFeedTrigger > 0) doRefresh(onDone = onRefreshDone)
    }

    // When current job is cleared, pick next pending job so we poll one by one (avoids scope.launch inside polling being cancelled).
    LaunchedEffect(lastIngestJobId) {
        if (lastIngestJobId != null) return@LaunchedEffect
        val pending = RefreshAndHighlightPrefs.getPendingIngestJobIds(context)
        if (pending.isNotEmpty()) lastIngestJobId = pending.first()
    }

    // Clear lastIngestJobId and immediately load next pending job in one place so the second (and later) jobs
    // are always picked up. Avoids relying on refill effect running after clear; fixes second card staying pending.
    LaunchedEffect(pendingClearPollingJobId) {
        val jobId = pendingClearPollingJobId ?: return@LaunchedEffect
        lastIngestJobId = null
        pendingClearPollingJobId = null
        val pending = RefreshAndHighlightPrefs.getPendingIngestJobIds(context)
        if (pending.isNotEmpty()) lastIngestJobId = pending.first()
        if (BuildConfig.DEBUG) {
            Log.d(TAG_FEED_INGEST, "after clear: pending=${pending.size} ids=${pending.take(3).joinToString(",")}${if (pending.size > 3) "..." else ""}, next lastIngestJobId=${pending.firstOrNull()}")
        }
    }

    // Bounded polling: max INGEST_POLL_MAX_COUNT times, plus withTimeout so we never poll indefinitely.
    // On done/failed/err/timeout we set pendingClearPollingJobId (not lastIngestJobId) so the clear runs in
    // a separate LaunchedEffect and this one is not cancelled before state (e.g. addIngestFailure) is applied.
    LaunchedEffect(lastIngestJobId) {
        val jobId = lastIngestJobId ?: return@LaunchedEffect
        if (BuildConfig.DEBUG) Log.d(TAG_FEED_INGEST, "polling jobId=$jobId")
        try {
            withTimeout(INGEST_POLL_TIMEOUT_MS) {
                var count = 0
                while (count < INGEST_POLL_MAX_COUNT) {
                    val intervalMs = if (count < INGEST_POLL_FAST_COUNT) INGEST_POLL_INTERVAL_FAST_MS else INGEST_POLL_INTERVAL_MS
                    kotlinx.coroutines.delay(intervalMs)
                    count++
                    when (val r = IngestRepository.getStatus(jobId)) {
                        is IngestRepository.StatusResponse.Ok -> {
                            when (r.status.state) {
                                "done" -> {
                                    RefreshAndHighlightPrefs.removePendingIngestJobIdSync(context, jobId)
                                    OnboardingPrefs.markFirstIngestCompletedSync(context)
                                    loadPage(0, append = false)
                                    snackbarHostState.showSnackbar("Added to your documents", withDismissAction = true)
                                    pendingClearPollingJobId = jobId
                                    return@withTimeout
                                }
                                "failed" -> {
                                    RefreshAndHighlightPrefs.removePendingIngestJobIdSync(context, jobId)
                                    addIngestFailure(
                                        IngestFailureInfo(
                                            message = shortIngestFailureMessage(
                                                r.status.failCode,
                                                r.status.errorCode,
                                                r.status.error
                                            ),
                                            errorCode = r.status.errorCode,
                                            failCode = r.status.failCode,
                                            sourceId = r.status.sourceId,
                                            jobId = jobId
                                        )
                                    )
                                    kotlinx.coroutines.yield()
                                    pendingClearPollingJobId = jobId
                                    return@withTimeout
                                }
                                else -> { /* queued/running, keep polling */ }
                            }
                        }
                        is IngestRepository.StatusResponse.Err -> {
                            if (BuildConfig.DEBUG) Log.w(TAG_FEED_INGEST, "getStatus Err jobId=$jobId message=${r.message}")
                            RefreshAndHighlightPrefs.removePendingIngestJobIdSync(context, jobId)
                            snackbarHostState.showSnackbar("Could not check status: ${r.message}", withDismissAction = true)
                            pendingClearPollingJobId = jobId
                            return@withTimeout
                        }
                    }
                }
                RefreshAndHighlightPrefs.removePendingIngestJobIdSync(context, jobId)
                snackbarHostState.showSnackbar("Ingest is still processing. Refresh the list later.", withDismissAction = true)
                pendingClearPollingJobId = jobId
            }
        } catch (_: TimeoutCancellationException) {
            RefreshAndHighlightPrefs.removePendingIngestJobIdSync(context, jobId)
            snackbarHostState.showSnackbar("Ingest is still processing. Refresh the list later.", withDismissAction = true)
            pendingClearPollingJobId = jobId
        }
    }

    Scaffold(snackbarHost = { SnackbarHost(snackbarHostState) }) { paddingValues ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            // URL input + Refresh
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                OutlinedTextField(
                    value = urlText,
                    onValueChange = { urlText = it },
                    label = { Text("Enter URL") },
                    modifier = Modifier.weight(1f),
                    singleLine = true
                )
                Spacer(modifier = Modifier.width(8.dp))
                IconButton(
                    onClick = { pdfPickerLauncher.launch("application/pdf") },
                    enabled = !isIngesting
                ) {
                    if (isIngesting) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(24.dp),
                            strokeWidth = 2.dp
                        )
                    } else {
                        Icon(Icons.Default.Upload, contentDescription = "파일 선택")
                    }
                }
                IconButton(
                    onClick = { doRefresh() },
                    enabled = !isRefreshing
                ) {
                    Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                }
                IconButton(
                    onClick = {
                        val url = urlText.trim()
                        if (url.isEmpty()) return@IconButton
                        isIngesting = true
                        scope.launch {
                            when (val r = IngestRepository.ingestUrl(url)) {
                                is IngestRepository.Result.Success -> {
                                    urlText = ""
                                    RefreshAndHighlightPrefs.setPendingIngestJobIdSync(context, r.jobId)
                                    lastIngestJobId = r.jobId
                                    snackbarHostState.showSnackbar(
                                        "Queued. Checking result…",
                                        withDismissAction = true
                                    )
                                }
                                is IngestRepository.Result.Error ->
                                    snackbarHostState.showSnackbar("Error: ${r.message}", withDismissAction = true)
                            }
                            isIngesting = false
                        }
                    },
                    enabled = !isIngesting
                ) {
                    if (isIngesting) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(24.dp),
                            strokeWidth = 2.dp
                        )
                    } else {
                        Icon(Icons.AutoMirrored.Filled.Send, contentDescription = "Send URL")
                    }
                }
            }

            // Selected document chip (when one is selected) — tap Deselect to clear
            if (selectedDocumentId != null) {
                val selected = documents.find { it.id == selectedDocumentId }
                if (selected != null) {
                    Surface(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 4.dp),
                        color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.6f),
                        shape = MaterialTheme.shapes.small
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            val name = selected.title?.takeIf { it.isNotBlank() }
                                ?: selected.url?.substringAfterLast('/')?.take(50)
                                ?: "Document"
                            Text(
                                text = "RAG will use: ${name.take(45)}${if (name.length > 45) "…" else ""}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onPrimaryContainer,
                                modifier = Modifier.weight(1f)
                            )
                            TextButton(onClick = onDocumentDeselect) {
                                Text("Deselect", style = MaterialTheme.typography.labelMedium)
                            }
                        }
                    }
                }
            }

            // Document list (or loading / empty / error state)
            when {
                isLoading && documents.isEmpty() -> {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(24.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            CircularProgressIndicator()
                            Spacer(modifier = Modifier.height(16.dp))
                            Text(
                                text = "Loading your documents…",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
                loadError != null && documents.isEmpty() -> {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(24.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                text = "Could not load documents",
                                style = MaterialTheme.typography.titleSmall,
                                color = MaterialTheme.colorScheme.error
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(
                                text = loadError ?: "",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(modifier = Modifier.height(16.dp))
                            TextButton(onClick = { loadPage(0, append = false) }) {
                                Text("Retry")
                            }
                        }
                    }
                }
                documents.isEmpty() -> {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(24.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                text = "No documents yet",
                                style = MaterialTheme.typography.titleSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(
                                text = "Add a PDF or URL above to ingest. Documents are listed per account.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(modifier = Modifier.height(12.dp))
                            Text(
                                text = "Then tap a card to select it and ask questions in the Ask tab.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.primary
                            )
                        }
                    }
                }
                else -> {
                    PullToRefreshBox(
                        isRefreshing = isRefreshing,
                        onRefresh = { doRefresh() },
                        modifier = Modifier.fillMaxSize()
                    ) {
                        LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(vertical = 8.dp)
                        ) {
                            items(documents) { doc ->
                                DocumentCard(
                                    document = doc,
                                    isSelected = doc.id == selectedDocumentId,
                                    isHighlighted = doc.id in highlightedDocumentIds,
                                    onSelect = {
                                        doDocumentSeen(doc.id)
                                        val displayName = doc.title?.takeIf { it.isNotBlank() }
                                            ?: doc.url?.substringAfterLast('/')?.take(60)
                                            ?: "Document"
                                        onDocumentSelect(doc.id, displayName)
                                    },
                                    onAddNote = { addNoteForDocument = doc },
                                    onOpen = {
                                        doDocumentSeen(doc.id)
                                        onCardClick(doc.id)
                                    },
                                    onRefresh = { doRefresh() },
                                    onTriggerWorker = { doTriggerWorker() },
                                    onDelete = { deleteConfirmDocumentId = doc.id },
                                    onReprocess = { doReprocessDocument(doc.id) }
                                )
                            }

                            if (loadMoreEnabled && documents.isNotEmpty()) {
                                item {
                                    Button(
                                        onClick = { loadPage(documents.size, append = true) },
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .padding(16.dp),
                                        enabled = !isLoading
                                    ) {
                                        Text(if (isLoading) "Loading…" else "Load more")
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // Dialogs on top of everything (compose order: later = on top)
    if (deleteConfirmDocumentId != null) {
        AlertDialog(
            onDismissRequest = { if (!isDeletingDocument) deleteConfirmDocumentId = null },
            title = { Text("Delete document?") },
            text = { Text("This will remove it from the server. This cannot be undone.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        if (!isDeletingDocument) deleteConfirmDocumentId?.let { doDeleteDocument(it) }
                    },
                    enabled = !isDeletingDocument,
                    colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error)
                ) {
                    if (isDeletingDocument) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(16.dp),
                                strokeWidth = 2.dp
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Deleting…")
                        }
                    } else {
                        Text("Delete")
                    }
                }
            },
            dismissButton = {
                TextButton(
                    onClick = { if (!isDeletingDocument) deleteConfirmDocumentId = null },
                    enabled = !isDeletingDocument
                ) {
                    Text("Cancel")
                }
            }
        )
    }

    if (addNoteForDocument != null) {
        val doc = addNoteForDocument!!
        NoteBottomSheet(
            documentId = doc.id,
            documentTitle = doc.title?.takeIf { it.isNotBlank() } ?: doc.url?.take(50) ?: "Document",
            onDismiss = { addNoteForDocument = null },
            onSave = { title, content, _ ->
                addNoteForDocument = null
                scope.launch {
                    val body = NotesApi.CreateNoteRequest(
                        content = content,
                        source_id = doc.id,
                        topic = title.takeIf { it.isNotBlank() }
                    )
                    val res = ApiClient.notesApi.createNote(body)
                    if (res.isSuccessful) {
                        snackbarHostState.showSnackbar("Note saved", withDismissAction = true)
                    } else {
                        snackbarHostState.showSnackbar("Failed to save note", withDismissAction = true)
                    }
                }
            }
        )
    }
}

@Preview(showBackground = true)
@Composable
fun FeedScreenPreview() {
    TekLearningAgentTheme {
        FeedScreen(
            selectedDocumentId = null,
            onDocumentSelect = { _, _ -> },
            onDocumentDeselect = {},
            onDocumentDeleted = {},
            onCardClick = {}
        )
    }
}
