package com.example.learning.agent.ui.components

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.example.learning.agent.R

@Composable
fun OnboardingDialog(
    onStart: () -> Unit,
    onSkip: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onSkip,
        title = { Text(stringResource(R.string.onboarding_title)) },
        text = {
            Column {
                Text(
                    text = stringResource(R.string.onboarding_body),
                    style = MaterialTheme.typography.bodyMedium
                )
                Spacer(modifier = Modifier.height(12.dp))
                Text(
                    text = stringResource(R.string.onboarding_step_1),
                    style = MaterialTheme.typography.bodySmall
                )
                Text(
                    text = stringResource(R.string.onboarding_step_2),
                    style = MaterialTheme.typography.bodySmall
                )
                Text(
                    text = stringResource(R.string.onboarding_step_3),
                    style = MaterialTheme.typography.bodySmall
                )
            }
        },
        confirmButton = {
            TextButton(onClick = onStart) {
                Text(stringResource(R.string.onboarding_cta_start))
            }
        },
        dismissButton = {
            TextButton(onClick = onSkip) {
                Text(stringResource(R.string.onboarding_cta_skip))
            }
        }
    )
}
