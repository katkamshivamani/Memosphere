"""
Windows Hello Biometric and User Consent Provider using Windows.Security.Credentials.UI.UserConsentVerifier.
"""
import subprocess

from local_security.platform.base import (
    BiometricAvailability,
    BiometricProvider,
    BiometricVerificationStatus,
)


class WindowsHelloBiometricProvider(BiometricProvider):
    """
    Integrates directly with Windows Hello via the official WinRT UserConsentVerifier API.
    Supports fingerprint, facial recognition, and Windows Hello PIN user consent.
    Does NOT handle, collect, or store biometric templates/fingerprints directly.
    """

    def check_availability(self) -> BiometricAvailability:
        ps_script = """
        try {
            Add-Type -AssemblyName System.Runtime.WindowsRuntime
            $asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() |
                Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' }

            $op = [Windows.Security.Credentials.UI.UserConsentVerifier, Windows.Security.Credentials.UI, ContentType=WindowsRuntime]::CheckAvailabilityAsync()
            $netTask = $asTaskGeneric[0].MakeGenericMethod([Windows.Security.Credentials.UI.UserConsentVerifierAvailability, Windows.Security.Credentials.UI, ContentType=WindowsRuntime]).Invoke($null, @($op))
            $netTask.Wait(5000)
            Write-Output "AVAILABILITY:$($netTask.Result)"
        } catch {
            Write-Output "ERROR:$($_.Exception.Message)"
        }
        """
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=8,
            )
            stdout = res.stdout.strip()
            for line in stdout.splitlines():
                line = line.strip()
                if line.startswith("AVAILABILITY:"):
                    status_str = line.split(":", 1)[1].strip()
                    status_map = {
                        "Available": BiometricAvailability.AVAILABLE,
                        "DeviceNotPresent": BiometricAvailability.DEVICE_NOT_PRESENT,
                        "NotConfiguredForUser": BiometricAvailability.NOT_CONFIGURED,
                        "DisabledByPolicy": BiometricAvailability.DISABLED_BY_POLICY,
                        "DeviceBusy": BiometricAvailability.DEVICE_BUSY,
                    }
                    return status_map.get(status_str, BiometricAvailability.UNKNOWN_ERROR)
                elif line.startswith("ERROR:"):
                    return BiometricAvailability.UNKNOWN_ERROR

            return BiometricAvailability.UNKNOWN_ERROR
        except Exception:
            return BiometricAvailability.UNKNOWN_ERROR

    def verify_user(self, prompt_message: str) -> tuple[BiometricVerificationStatus, str | None]:
        # Sanitize prompt message for PowerShell string
        safe_msg = prompt_message.replace('"', '""').replace("`", "")
        ps_script = f"""
        try {{
            Add-Type -AssemblyName System.Runtime.WindowsRuntime
            $asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() |
                Where-Object {{ $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' }}

            $msg = "{safe_msg}"
            $op = [Windows.Security.Credentials.UI.UserConsentVerifier, Windows.Security.Credentials.UI, ContentType=WindowsRuntime]::RequestVerificationAsync($msg)
            $netTask = $asTaskGeneric[0].MakeGenericMethod([Windows.Security.Credentials.UI.UserConsentVerificationResult, Windows.Security.Credentials.UI, ContentType=WindowsRuntime]).Invoke($null, @($op))
            $netTask.Wait(60000)
            Write-Output "RESULT:$($netTask.Result)"
        }} catch {{
            Write-Output "ERROR:$($_.Exception.Message)"
        }}
        """
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=65,
            )
            stdout = res.stdout.strip()
            for line in stdout.splitlines():
                line = line.strip()
                if line.startswith("RESULT:"):
                    res_str = line.split(":", 1)[1].strip()
                    if res_str == "Verified":
                        return BiometricVerificationStatus.VERIFIED, "Windows Hello verification succeeded"
                    elif res_str == "Canceled":
                        return BiometricVerificationStatus.CANCELED, "User canceled Windows Hello prompt"
                    elif res_str == "RetriesExhausted":
                        return BiometricVerificationStatus.RETRIES_EXHAUSTED, "Maximum verification retries exhausted"
                    elif res_str == "DeviceBusy":
                        return BiometricVerificationStatus.DEVICE_BUSY, "Biometric hardware is busy"
                    elif res_str in ("DeviceNotPresent", "NotConfiguredForUser", "DisabledByPolicy"):
                        return BiometricVerificationStatus.HARDWARE_UNAVAILABLE, f"Biometric verification unavailable: {res_str}"
                    else:
                        return BiometricVerificationStatus.FAILED, f"Verification failed with status: {res_str}"
                elif line.startswith("ERROR:"):
                    return BiometricVerificationStatus.FAILED, line

            return BiometricVerificationStatus.FAILED, "No response from Windows Hello subsystem"
        except subprocess.TimeoutExpired:
            return BiometricVerificationStatus.CANCELED, "Windows Hello prompt timed out"
        except Exception as e:
            return BiometricVerificationStatus.FAILED, str(e)
