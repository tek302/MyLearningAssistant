package com.example.learning.agent

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.rememberNavController
import com.example.learning.agent.data.repository.IngestRepository
import com.example.learning.agent.data.repository.RefreshAndHighlightPrefs
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
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val sharedUrl = consumeSendIntentUrl(intent)
        if (sharedUrl != null) {
            runHeadlessIngest(sharedUrl)
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
        val sharedUrl = consumeSendIntentUrl(intent)
        if (sharedUrl != null) {
            runHeadlessIngest(sharedUrl)
        }
    }

    /** Returns URL if this was a SEND intent with text, and consumes the intent. */
    private fun consumeSendIntentUrl(intent: Intent?): String? {
        if (intent?.action != Intent.ACTION_SEND || intent.type != "text/plain") return null
        val url = intent.getStringExtra(Intent.EXTRA_TEXT)?.trim()?.takeIf { it.isNotEmpty() }
        setIntent(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER))
        return url
    }

    /** Queue ingest and finish so user returns to the app they shared from (e.g. Chrome). */
    private fun runHeadlessIngest(url: String) {
        if (FirebaseAuth.getInstance().currentUser == null) {
            Toast.makeText(this, "Sign in to add documents", Toast.LENGTH_SHORT).show()
            finish()
            return
        }
        setContent {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("Adding document…", style = MaterialTheme.typography.bodyLarge)
            }
        }
        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) { IngestRepository.ingestUrl(url) }
            withContext(Dispatchers.Main) {
                when (result) {
                    is IngestRepository.Result.Success -> {
                        RefreshAndHighlightPrefs.setRefreshFromShareAtSync(applicationContext)
                        Toast.makeText(this@MainActivity, "Added to your documents", Toast.LENGTH_SHORT).show()
                    }
                    is IngestRepository.Result.Error ->
                        Toast.makeText(this@MainActivity, "Error: ${result.message}", Toast.LENGTH_LONG).show()
                }
                finish()
            }
        }
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
            modifier = Modifier.padding(paddingValues)
        )
    }
}