package com.example.learning.agent.ui.screens.recommendations

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.learning.agent.data.models.Recommendation
import com.example.learning.agent.data.repository.IngestRepository
import com.example.learning.agent.data.repository.RecommendationsRepository
import com.example.learning.agent.ui.components.RecommendationCard
import com.example.learning.agent.ui.theme.TekLearningAgentTheme
import kotlinx.coroutines.launch
import java.util.Calendar

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecommendationsScreen(
    modifier: Modifier = Modifier
) {
    var selectedWeek by remember { mutableStateOf("All") }
    var selectedTopic by remember { mutableStateOf<String?>(null) }
    var recommendations by remember { mutableStateOf<List<Recommendation>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var isRefreshing by remember { mutableStateOf(false) }
    var loadError by remember { mutableStateOf<String?>(null) }
    var processInProgress by remember { mutableStateOf<String?>(null) }
    var removeInProgress by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }

    fun weekStartForLabel(label: String): String? = when (label) {
        "This Week" -> getWeekStartMonday(0)
        "Last Week" -> getWeekStartMonday(-1)
        else -> null
    }

    fun loadRecommendations(showRefresh: Boolean = false) {
        if (showRefresh) {
            if (isRefreshing) return
            isRefreshing = true
        } else {
            // Allow first load when recommendations is empty; skip only if already loading and we have data (prevent duplicate load)
            if (isLoading && recommendations.isNotEmpty()) return
            isLoading = true
        }
        loadError = null
        scope.launch {
            try {
                val weekStart = weekStartForLabel(selectedWeek)
                when (val r = RecommendationsRepository.list(
                    weekStart = weekStart,
                    topicName = selectedTopic,
                    limit = 50
                )) {
                    is RecommendationsRepository.ListResult.Success -> {
                        recommendations = r.items
                    }
                    is RecommendationsRepository.ListResult.Error -> {
                        loadError = r.message
                        snackbarHostState.showSnackbar("Error: ${r.message}")
                    }
                }
            } finally {
                isLoading = false
                isRefreshing = false
            }
        }
    }

    LaunchedEffect(selectedWeek, selectedTopic) {
        loadRecommendations()
    }

    val topics = remember(recommendations) {
        recommendations.map { it.topicName }.distinct().sorted()
    }

    PullToRefreshBox(
        isRefreshing = isRefreshing,
        onRefresh = { loadRecommendations(showRefresh = true) },
        modifier = modifier.fillMaxSize()
    ) {
        Scaffold(
            snackbarHost = { SnackbarHost(snackbarHostState) }
        ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(16.dp)
        ) {
            // Week dropdown
            var expandedWeek by remember { mutableStateOf(false) }
            ExposedDropdownMenuBox(
                expanded = expandedWeek,
                onExpandedChange = { expandedWeek = !expandedWeek },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 16.dp)
            ) {
                OutlinedTextField(
                    value = selectedWeek,
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Time Range") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expandedWeek) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .menuAnchor()
                )
                ExposedDropdownMenu(
                    expanded = expandedWeek,
                    onDismissRequest = { expandedWeek = false }
                ) {
                    listOf("All", "This Week", "Last Week").forEach { week ->
                        DropdownMenuItem(
                            text = { Text(week) },
                            onClick = {
                                selectedWeek = week
                                expandedWeek = false
                            }
                        )
                    }
                }
            }

            // Topic chips
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState())
                    .padding(bottom = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                FilterChip(
                    selected = selectedTopic == null,
                    onClick = { selectedTopic = null },
                    label = { Text("All") }
                )
                topics.forEach { topic ->
                    FilterChip(
                        selected = selectedTopic == topic,
                        onClick = {
                            selectedTopic = if (selectedTopic == topic) null else topic
                        },
                        label = { Text(topic) }
                    )
                }
            }

            when {
                isLoading && recommendations.isEmpty() -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator()
                    }
                }
                loadError != null && recommendations.isEmpty() -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                text = loadError ?: "Error",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.error
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            Button(onClick = { loadRecommendations() }) {
                                Icon(Icons.Default.Refresh, contentDescription = null)
                                Spacer(modifier = Modifier.width(8.dp))
                                Text("Retry")
                            }
                        }
                    }
                }
                recommendations.isEmpty() -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = "No recommendations yet. Complete an S2 weekly summary to get arXiv suggestions.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                else -> {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = PaddingValues(vertical = 8.dp)
                    ) {
                        items(recommendations) { rec ->
                            RecommendationCard(
                                recommendation = rec,
                                onProcess = {
                                    if (processInProgress == rec.id) return@RecommendationCard
                                    processInProgress = rec.id
                                    scope.launch {
                                        when (val ingest = IngestRepository.ingestUrl(rec.url, rec.title)) {
                                            is IngestRepository.Result.Success -> {
                                                val deleted = RecommendationsRepository.delete(rec.id)
                                                if (deleted) {
                                                    recommendations = recommendations - rec
                                                    snackbarHostState.showSnackbar("Queued for ingest. Removed from list.")
                                                } else {
                                                    snackbarHostState.showSnackbar("Queued for ingest. Could not remove from list.")
                                                }
                                            }
                                            is IngestRepository.Result.Error -> {
                                                snackbarHostState.showSnackbar("Ingest failed: ${ingest.message}")
                                            }
                                        }
                                        processInProgress = null
                                    }
                                },
                                onRemove = {
                                    if (removeInProgress == rec.id) return@RecommendationCard
                                    removeInProgress = rec.id
                                    scope.launch {
                                        val deleted = RecommendationsRepository.delete(rec.id)
                                        if (deleted) {
                                            recommendations = recommendations - rec
                                            snackbarHostState.showSnackbar("Removed from list.")
                                        } else {
                                            snackbarHostState.showSnackbar("Could not remove.")
                                        }
                                        removeInProgress = null
                                    }
                                }
                            )
                        }
                    }
                }
            }
        }
    }
    }
}

/** Returns Monday of the week as YYYY-MM-DD. offsetWeeks 0 = this week, -1 = last week. */
private fun getWeekStartMonday(offsetWeeks: Int): String {
    val cal = Calendar.getInstance()
    cal.firstDayOfWeek = Calendar.MONDAY
    cal.set(Calendar.DAY_OF_WEEK, Calendar.MONDAY)
    cal.add(Calendar.WEEK_OF_YEAR, offsetWeeks)
    val y = cal.get(Calendar.YEAR)
    val m = cal.get(Calendar.MONTH) + 1
    val d = cal.get(Calendar.DAY_OF_MONTH)
    return "%04d-%02d-%02d".format(y, m, d)
}

@Preview(showBackground = true)
@Composable
fun RecommendationsScreenPreview() {
    TekLearningAgentTheme {
        RecommendationsScreen()
    }
}
