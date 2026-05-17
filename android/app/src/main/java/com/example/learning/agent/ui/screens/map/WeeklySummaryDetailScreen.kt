package com.example.learning.agent.ui.screens.map

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.example.learning.agent.data.remote.S2Api
import com.example.learning.agent.data.repository.S2Repository
import com.example.learning.agent.data.repository.ThreadPrefs
import com.example.learning.agent.ui.components.formatS2PeriodLine
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WeeklySummaryDetailScreen(
    id: String,
    onBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    var summary by remember { mutableStateOf<S2Api.S2SummaryItem?>(null) }
    var loading by remember { mutableStateOf(true) }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current.applicationContext

    LaunchedEffect(id) {
        scope.launch {
            when (val r = S2Repository.getS2Summaries(limit = 50, threadId = ThreadPrefs.getSelectedThreadId(context))) {
                is S2Repository.Result.Success ->
                    summary = r.summaries.find { it.id == id }
                is S2Repository.Result.Error -> summary = null
            }
            loading = false
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Weekly Summary") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { paddingValues ->
        if (loading) {
            Box(
                modifier = modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator()
            }
        } else if (summary == null) {
            Box(
                modifier = modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentAlignment = Alignment.Center
            ) {
                Text("Summary not found")
            }
        } else {
            val s = summary!!
            val weekLabel = formatS2PeriodLine(s.extra)
                ?: s.extra?.weekStart?.let { "Week of $it" }
                ?: s.extra?.topicName ?: "This Week"
            val sections = s.extra?.sections?.filter { it.insights.isNotEmpty() }.orEmpty()
            val isV2 = sections.isNotEmpty()
            val bullets = s.bullets?.filter { it.isNotBlank() }.orEmpty()

            Column(
                modifier = modifier
                    .fillMaxSize()
                    .padding(paddingValues)
                    .verticalScroll(rememberScrollState())
                    .padding(16.dp)
            ) {
                Text(
                    text = weekLabel,
                    style = MaterialTheme.typography.headlineSmall,
                    color = MaterialTheme.colorScheme.primary
                )
                Spacer(modifier = Modifier.height(16.dp))
                s.tldr?.takeIf { it.isNotBlank() }?.let { tldr ->
                    Text(
                        text = tldr,
                        style = MaterialTheme.typography.bodyLarge,
                        textAlign = TextAlign.Justify,
                        modifier = Modifier.padding(bottom = 16.dp)
                    )
                }

                if (isV2) {
                    S2V2Content(sections, s.extra)
                }

                if (bullets.isNotEmpty()) {
                    SectionHeader(if (isV2) "All Key Points" else "Key Points")
                    bullets.forEach { bullet ->
                        BulletRow(bullet)
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun S2V2Content(
    sections: List<S2Api.S2Section>,
    extra: S2Api.S2Extra?,
) {
    // --- Keyword sections ---
    sections.forEach { sec ->
        SectionHeader("${sec.keyword}  (${sec.docCount} docs)")
        sec.insights.forEach { insight ->
            BulletRow(insight)
        }
        Spacer(modifier = Modifier.height(8.dp))
    }

    // --- Emerging topics ---
    val emerging = extra?.emergingTopics?.filter { it.isNotBlank() }.orEmpty()
    if (emerging.isNotEmpty()) {
        SectionHeader("Emerging Topics")
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            emerging.forEach { topic ->
                SuggestionChip(
                    onClick = {},
                    label = { Text(topic, style = MaterialTheme.typography.labelSmall) }
                )
            }
        }
        Spacer(modifier = Modifier.height(12.dp))
    }

    // --- Connections ---
    val connections = extra?.connections?.filter { it.insight.isNotBlank() }.orEmpty()
    if (connections.isNotEmpty()) {
        SectionHeader("Cross-Document Connections")
        connections.forEach { conn ->
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 4.dp),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                )
            ) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Text(
                        text = conn.docs.joinToString(" & "),
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.primary
                    )
                    Text(
                        text = conn.insight,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(top = 4.dp)
                    )
                }
            }
        }
        Spacer(modifier = Modifier.height(12.dp))
    }

    // --- Trajectory ---
    val traj = extra?.trajectory
    if (traj != null) {
        val deepened = traj.deepened?.filter { it.isNotBlank() }.orEmpty()
        val newTopics = traj.newThisWeek?.filter { it.isNotBlank() }.orEmpty()
        val paused = traj.paused?.filter { it.isNotBlank() }.orEmpty()
        if (deepened.isNotEmpty() || newTopics.isNotEmpty() || paused.isNotEmpty()) {
            SectionHeader("Learning Trajectory")
            if (deepened.isNotEmpty()) {
                TrajectoryGroup(label = "Deepened", items = deepened)
            }
            if (newTopics.isNotEmpty()) {
                TrajectoryGroup(label = "New this week", items = newTopics)
            }
            if (paused.isNotEmpty()) {
                TrajectoryGroup(label = "Paused", items = paused)
            }
            Spacer(modifier = Modifier.height(12.dp))
        }
    }

    // --- Reflection ---
    extra?.reflection?.takeIf { it.isNotBlank() }?.let { refl ->
        SectionHeader("Reflection")
        Text(
            text = refl,
            style = MaterialTheme.typography.bodyMedium,
            fontStyle = FontStyle.Italic,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 16.dp)
        )
    }
}

@Composable
private fun TrajectoryGroup(label: String, items: List<String>) {
    Text(
        text = label,
        style = MaterialTheme.typography.labelMedium,
        fontWeight = FontWeight.Medium,
        color = MaterialTheme.colorScheme.tertiary,
        modifier = Modifier.padding(top = 4.dp, bottom = 2.dp)
    )
    items.forEach { item -> BulletRow(item) }
}

@Composable
private fun SectionHeader(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.titleMedium,
        modifier = Modifier.padding(top = 12.dp, bottom = 6.dp)
    )
}

@Composable
private fun BulletRow(text: String) {
    Row(modifier = Modifier.padding(vertical = 3.dp)) {
        Text(
            text = "• ",
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.primary
        )
        Text(
            text = text,
            style = MaterialTheme.typography.bodyLarge,
            modifier = Modifier.weight(1f)
        )
    }
}
