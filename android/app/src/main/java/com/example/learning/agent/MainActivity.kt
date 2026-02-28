package com.example.learning.agent

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.rememberNavController
import com.example.learning.agent.ui.auth.AuthViewModel
import com.example.learning.agent.ui.navigation.*
import com.example.learning.agent.ui.screens.signin.SignInScreen
import com.example.learning.agent.ui.theme.TekLearningAgentTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            TekLearningAgentTheme {
                RootContent()
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