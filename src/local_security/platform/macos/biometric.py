"""
macOS Touch ID / LocalAuthentication biometric adapter.
"""
import subprocess

from local_security.platform.base import (
    BiometricAvailability,
    BiometricProvider,
    BiometricVerificationStatus,
)


class MacOSTouchIDBiometricProvider(BiometricProvider):
    """
    macOS Touch ID integration via LocalAuthentication (LAContext).
    Uses a minimal swift script or osascript to evaluate policy deviceOwnerAuthenticationWithBiometrics.
    """

    def check_availability(self) -> BiometricAvailability:
        swift_code = """
        import LocalAuthentication
        let context = LAContext()
        var error: NSError?
        if context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error) {
            print("AVAILABLE")
        } else if let err = error {
            if err.code == LAError.biometryNotAvailable.rawValue {
                print("DEVICE_NOT_PRESENT")
            } else if err.code == LAError.biometryNotEnrolled.rawValue {
                print("NOT_CONFIGURED")
            } else {
                print("UNAVAILABLE")
            }
        } else {
            print("UNAVAILABLE")
        }
        """
        try:
            res = subprocess.run(
                ["swift", "-e", swift_code],
                capture_output=True,
                text=True,
                timeout=5,
            )
            out = res.stdout.strip()
            status_map = {
                "AVAILABLE": BiometricAvailability.AVAILABLE,
                "DEVICE_NOT_PRESENT": BiometricAvailability.DEVICE_NOT_PRESENT,
                "NOT_CONFIGURED": BiometricAvailability.NOT_CONFIGURED,
            }
            return status_map.get(out, BiometricAvailability.DEVICE_NOT_PRESENT)
        except Exception:
            return BiometricAvailability.UNSUPPORTED_PLATFORM

    def verify_user(self, prompt_message: str) -> tuple[BiometricVerificationStatus, str | None]:
        escaped_prompt = prompt_message.replace('"', '\\"')
        swift_code = f"""
        import LocalAuthentication
        import Foundation
        let context = LAContext()
        let semaphore = DispatchSemaphore(value: 0)
        var resultStatus = "FAILED"
        var resultMsg = ""
        context.evaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, localizedReason: "{escaped_prompt}") {{ success, error in
            if success {{
                resultStatus = "VERIFIED"
            }} else if let err = error as? LAError {{
                if err.code == .userCancel {{
                    resultStatus = "CANCELED"
                }} else {{
                    resultStatus = "FAILED"
                    resultMsg = err.localizedDescription
                }}
            }}
            semaphore.signal()
        }}
        _ = semaphore.wait(timeout: .now() + 30)
        print("\\(resultStatus):\\(resultMsg)")
        """
        try:
            res = subprocess.run(
                ["swift", "-e", swift_code],
                capture_output=True,
                text=True,
                timeout=35,
            )
            out = res.stdout.strip()
            if out.startswith("VERIFIED"):
                return BiometricVerificationStatus.VERIFIED, "Touch ID verified"
            elif out.startswith("CANCELED"):
                return BiometricVerificationStatus.CANCELED, "User canceled Touch ID prompt"
            else:
                return BiometricVerificationStatus.FAILED, out
        except subprocess.TimeoutExpired:
            return BiometricVerificationStatus.CANCELED, "Touch ID prompt timed out"
        except Exception as e:
            return BiometricVerificationStatus.FAILED, str(e)
