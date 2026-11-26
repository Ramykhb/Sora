# Build and sideload Sora on iPhone from Windows

GitHub Actions builds a standalone iPhone Release with Expo SDK 58, Xcode 26.6, and CocoaPods. The IPA contains the JavaScript bundle and assets and runs without Metro. Windows handles the download and installation. Signing happens in Sideloadly with a free Apple Account. See the [Expo SDK toolchain requirements](https://docs.expo.dev/versions/v58.0.0/#support-for-android-and-ios-versions).

## Build and download

1. Create an empty **private** GitHub build repository without initializing a README. From the Sora checkout, commit the build changes on `feature/ios-sideload-build` and push that branch to the private repository. Set it as the build repository's default under **Settings → General** if GitHub hasn't already selected it. GitHub requires `workflow_dispatch` to exist on the default branch before you can run it. [GitHub manual workflow requirements](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)

   ```powershell
   git switch feature/ios-sideload-build
   git add .github/workflows/build-ios.yml mobile/app.json mobile/README.md mobile/docs/ios-sideload.md
   git commit -m "Add unsigned iOS build for Windows sideloading"
   git remote add ios-build https://github.com/YOUR-ACCOUNT/sora-ios-build.git
   git push ios-build feature/ios-sideload-build
   ```

2. For a deployed backend, optionally set the repository Actions **variable** `EXPO_PUBLIC_API_URL` to the public HTTPS origin, such as `https://sora.example.com`. Leave it unset for a LAN setup and use **Change server** on the device. The value is visible in the compiled app. Keep database, AI provider, TURN, and Apple credentials out of this variable. CI builds with Expo dotenv loading disabled.
3. Under **Actions → Build unsigned Sora iOS IPA → Run workflow**, select the branch and start the run. This uses your private repository's GitHub Actions allowance. Check the account's remaining usage and spending controls before dispatching. [GitHub Actions billing](https://docs.github.com/en/actions/concepts/billing-and-usage)
4. Open the successful run, download **Sora-ios-unsigned** under **Artifacts**, and extract `Sora.ipa` from GitHub's download. Keep the IPA intact. The artifact expires after seven days. Save a local copy for refreshes.

## Install and refresh

1. Install Sideloadly for Windows and the web versions of iTunes and iCloud linked on its download page. Connect the iPhone over USB, unlock it, and tap **Trust This Computer** if prompted. [Sideloadly downloads and Windows prerequisites](https://sideloadly.io/)
2. Select the iPhone in Sideloadly, load `Sora.ipa`, enter your Apple Account, and click **Start**. Complete Apple's authentication prompts on Windows. Keep the same Apple Account and any Sideloadly bundle ID override across reinstalls so iOS can update the existing app.
3. On the iPhone, enable **Settings → Privacy & Security → Developer Mode**, restart when prompted, and confirm **Turn On**. If that setting is missing, attempt the USB installation first and check again. If iOS asks you to trust the developer, go to **Settings → General → VPN & Device Management**, select your developer profile, and follow the trust prompt. [Apple Developer Mode instructions](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device)
4. Open Sora from the Home Screen. Grant camera, microphone, speech recognition, local network, and location access as prompted for the features you use.
5. Before the free provisioning profile expires after seven days, reinstall the same IPA with the same account and bundle ID, or enable Sideloadly's automatic refresh and keep its Windows daemon running with the paired iPhone reachable. See [Apple Personal Team limits](https://developer.apple.com/help/account/basics/about-your-developer-account) and the [Sideloadly refresh FAQ](https://sideloadly.io/#faq).

The app config resolves to an empty custom entitlements dictionary. Sora uses standard permissions, audio background mode, and the app's normal Keychain access through SecureStore. Sideloadly supplies the signing entitlements and profile. Push notifications, app groups, and associated domains are absent from the resolved Expo config.

## Connect to the backend

For Windows LAN development, run the [existing backend](../../backend/README.md) on an interface the iPhone can reach, with TCP port 8000 published by Docker or bound on `0.0.0.0`. Put both devices on the same network. Find the active Windows adapter's IPv4 address with `ipconfig`, allow the port on the Windows private firewall profile, and use **Change server** before signing in. Enter `http://<WINDOWS-LAN-IP>:8000` without `/api/v1`. `localhost` on the phone points back to the phone. Changing the server clears stored credentials. Use HTTPS for a deployed backend. The iOS cleartext exceptions cover the standard private IPv4 ranges. [Apple ATS exception domains](https://developer.apple.com/documentation/bundleresources/information-property-list/nsapptransportsecurity/nsexceptiondomains)

| Check | How to verify |
| --- | --- |
| REST | Open `<server-origin>/health` in iPhone Safari. Then sign in from Sora to verify the app's local network permission and API access. |
| WebSocket | Open a session and verify that live events arrive, such as new answers or alerts. With an HTTPS reverse proxy, forward WebSocket upgrades for the session events path so `wss://` works. |
| WebRTC | Start the camera and watch the **Received** frame count or dashboard video. SDP signaling uses authenticated HTTP. Media needs a working ICE path separately. For Docker on the LAN, set `TURN_PUBLIC_HOST` to the Windows LAN IP in `backend/.env`, run `docker compose --profile webrtc up -d turn` from `backend`, and recreate the API with `docker compose --profile webrtc up -d --force-recreate api`. Allow TURN TCP/UDP 3478 and relay UDP 48000–48099. A remote backend needs a relay reachable by both peers. See [WebRTC networking](../../backend/docs/environment.md#webrtc-networking). |

On the first device run, also record a question, try a spoken command, play a spoken answer, and reopen the app to confirm it retained the sign-in. Try a location question and a historical question against a session with retained frames.

## Troubleshooting

- **No Run workflow button** · Check that the workflow is on the build repository's default branch and that you have write access. A feature branch push alone does not register a new manual workflow on Sora's default branch.
- **Build failed** · Start with the first error in **Install locked dependencies**, **Install CocoaPods dependencies**, or **Build unsigned Release**. The job prints the Node, CocoaPods, Xcode, and iPhone SDK versions. If GitHub retires the selected Xcode path, check the [macOS runner image](https://github.com/actions/runner-images/blob/main/images/macos/macos-26-Readme.md#xcode) and the Expo minimum before changing it.
- **Device or signing error** · Unlock the iPhone and confirm it appears in the Apple device software. Check Developer Mode and profile trust. If Apple reports a bundle ID conflict, use Sideloadly's bundle ID override and reuse that same value for refreshes. Check your Personal Team's device and app ID limits if Apple refuses to provision.
- **REST works, video does not** · Check the local network and camera permissions, TURN host and ports, and whether the Wi-Fi isolates clients. A working HTTPS endpoint or WebSocket alone does not verify the ICE media path.
- **App stopped launching after a week** · Re-sign and install the saved IPA. To test new JavaScript or native changes, run the workflow again and install the new IPA.
