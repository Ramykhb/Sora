import { SymbolView } from 'expo-symbols';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

const colors = {
  ink: '#142820', muted: '#74847A', paper: '#F5F7F2', card: '#FFFFFF', green: '#245B45',
  mint: '#E3F0E8', lime: '#D7EF92', line: '#E8EDE7', orange: '#F1A374',
};

type IconName = 'camera.fill' | 'mic.fill' | 'waveform' | 'location.fill' | 'sun.max.fill' | 'arrow.up.right' | 'house.fill' | 'clock' | 'gearshape.fill' | 'pause.fill' | 'play.fill' | 'speaker.wave.2.fill' | 'chevron.right';

function Icon({ name, size = 18, color = colors.ink }: { name: IconName; size?: number; color?: string }) {
  return <SymbolView name={name} size={size} tintColor={color} />;
}

function Header() {
  return (
    <View style={styles.header}>
      <View style={styles.brandMark}><View style={styles.brandDot} /><View style={styles.brandDotSmall} /></View>
      <View style={styles.brandText}><Text style={styles.brandName}>sora</Text><Text style={styles.brandCaption}>YOUR EVERYDAY COMPANION</Text></View>
      <Pressable accessibilityLabel="Settings" style={styles.avatar}><Text style={styles.avatarText}>M</Text><View style={styles.onlineDot} /></Pressable>
    </View>
  );
}

function LiveStatus({ active, onToggle }: { active: boolean; onToggle: () => void }) {
  return (
    <View style={styles.liveRow}>
      <View style={[styles.liveIndicator, !active && styles.liveIndicatorOff]}><View style={[styles.liveDot, !active && styles.liveDotOff]} /><Text style={[styles.liveLabel, !active && styles.liveLabelOff]}>{active ? 'LIVE ASSIST' : 'ASSIST PAUSED'}</Text></View>
      <Text style={styles.liveHint}>{active ? 'Ready when you are' : 'Tap to resume'}</Text>
      <Pressable onPress={onToggle} accessibilityLabel={active ? 'Pause live assistance' : 'Resume live assistance'} style={styles.liveToggle}><Icon name={active ? 'pause.fill' : 'play.fill'} size={12} color={colors.green} /></Pressable>
    </View>
  );
}

function CameraPreview({ active }: { active: boolean }) {
  const [permission, requestPermission] = useCameraPermissions();

  return (
    <View style={styles.camera}>
      {active && permission?.granted && <CameraView style={styles.cameraFeed} facing="back" />}
      {active && permission && !permission.granted && (
        <Pressable onPress={requestPermission} style={styles.cameraPermission}>
          <View style={styles.permissionIcon}><Icon name="camera.fill" size={17} color={colors.green} /></View>
          <Text style={styles.permissionTitle}>Allow camera access</Text>
          <Text style={styles.permissionCopy}>Tap to show your live view</Text>
        </Pressable>
      )}
      {!permission && active && <View style={styles.cameraLoading}><Text style={styles.permissionCopy}>Opening camera…</Text></View>}
      <View style={styles.cameraTop}>
        <View style={styles.viewfinder}><View style={styles.vfCornerTL} /><View style={styles.vfCornerTR} /><View style={styles.vfCornerBL} /><View style={styles.vfCornerBR} /></View>
        <View style={styles.cameraChip}><View style={styles.cameraChipDot} /><Text style={styles.cameraChipText}>{active ? 'CAMERA ON' : 'CAMERA PAUSED'}</Text></View>
      </View>
      {(!active || !permission?.granted) && <View style={styles.scene}>
        <View style={styles.window}><View style={styles.windowPane} /><View style={styles.windowPane} /><View style={styles.windowPane} /><View style={styles.windowPane} /></View>
        <View style={styles.shelf}><View style={styles.plantPot}><View style={styles.plantLeaf} /><View style={styles.plantLeaf2} /></View><View style={styles.bookStack}><View /><View /><View /></View><View style={styles.cup} /></View>
        <View style={styles.table}><View style={styles.tableLeg} /><View style={styles.tableLeg2} /></View>
        <View style={styles.roomWall} /><View style={styles.roomFloor} />
      </View>}
      {permission?.granted && active && <View style={styles.cameraLiveCaption}><View style={styles.cameraChipDot} /><Text style={styles.sceneText}>Live camera preview</Text><Text style={styles.sceneTime}>back camera</Text></View>}
      {(!active || !permission?.granted) && <View style={styles.sceneCaption}><View style={styles.captionIcon}><Icon name="sun.max.fill" size={13} color="#C78043" /></View><Text style={styles.sceneText}>{active ? 'Camera preview is waiting' : 'Camera is paused'}</Text><Text style={styles.sceneTime}>{active ? 'tap to allow' : 'paused'}</Text></View>}
    </View>
  );
}

function ChatMessage({ who, children, time }: { who: 'sora' | 'you'; children: string; time: string }) {
  const fromSora = who === 'sora';
  return <View style={[styles.messageRow, !fromSora && styles.messageRowYou]}>{fromSora && <View style={styles.messageMark}><View /></View>}<View style={[styles.messageBubble, fromSora ? styles.soraBubble : styles.youBubble]}><Text style={[styles.messageText, !fromSora && styles.youText]}>{children}</Text><Text style={[styles.messageTime, !fromSora && styles.youTime]}>{time}</Text></View></View>;
}

function ChatList() {
  return <View style={styles.chatList}><ChatMessage who="sora" time="10:42 AM">There’s a ceramic mug on the table, next to a small stack of books. The window is open and it looks like a lovely day outside.</ChatMessage><ChatMessage who="you" time="10:43 AM">What does the note on the table say?</ChatMessage><ChatMessage who="sora" time="10:43 AM">It says, “Pick up groceries on the way home.”</ChatMessage></View>;
}

function VoiceButton({ listening, onPress }: { listening: boolean; onPress: () => void }) {
  return <Pressable onPress={onPress} accessibilityLabel={listening ? 'Stop listening' : 'Start voice question'} style={({ pressed }) => [styles.voiceButton, listening && styles.voiceButtonListening, pressed && { transform: [{ scale: 0.97 }] }]}><Icon name={listening ? 'waveform' : 'mic.fill'} size={20} color="#FFFFFF" /><Text style={styles.voiceButtonText}>{listening ? 'Listening… tap to stop' : 'Ask Sora anything'}</Text><View style={styles.voiceButtonArrow}><Icon name={listening ? 'waveform' : 'arrow.up.right'} size={14} color={colors.green} /></View></Pressable>;
}

function BottomNavigation({ current, onSelect }: { current: string; onSelect: (value: string) => void }) {
  const items: { label: string; icon: IconName }[] = [{ label: 'Today', icon: 'house.fill' }, { label: 'Moments', icon: 'clock' }, { label: 'Settings', icon: 'gearshape.fill' }];
  return <View style={styles.bottomNav}>{items.map((item) => <Pressable key={item.label} onPress={() => onSelect(item.label)} style={styles.navItem}><Icon name={item.icon} size={19} color={current === item.label ? colors.green : '#A3AEA5'} /><Text style={[styles.navLabel, current === item.label && styles.navLabelActive]}>{item.label}</Text>{current === item.label && <View style={styles.navUnderline} />}</Pressable>)}</View>;
}

export default function HomeScreen() {
  const [streamActive, setStreamActive] = useState(true);
  const [listening, setListening] = useState(false);
  const [currentTab, setCurrentTab] = useState('Today');
  const [showStatus, setShowStatus] = useState(false);
  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right']}>
      <Header />
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.greeting}><View><Text style={styles.eyebrow}>THURSDAY, OCTOBER 24</Text><Text style={styles.title}>Good morning, Maya</Text><Text style={styles.subtitle}>I’m right here whenever you need me.</Text></View><View style={styles.sunBadge}><Icon name="sun.max.fill" size={20} color="#B97841" /></View></View>
        <LiveStatus active={streamActive} onToggle={() => setStreamActive((value) => !value)} />
        <CameraPreview active={streamActive} />
        <View style={styles.sectionHeader}><View><Text style={styles.sectionTitle}>A little more context</Text><Text style={styles.sectionSubtitle}>Your conversation with Sora</Text></View><Pressable onPress={() => setShowStatus((value) => !value)} style={styles.moreButton}><Text style={styles.moreText}>{showStatus ? 'Hide' : 'View all'}</Text><Icon name="chevron.right" size={12} color={colors.green} /></Pressable></View>
        {showStatus && <View style={styles.statusCard}><View style={styles.statusIcon}><Icon name="speaker.wave.2.fill" size={15} color={colors.green} /></View><View style={{ flex: 1 }}><Text style={styles.statusTitle}>Sora is here with you</Text><Text style={styles.statusCopy}>Your assistant is ready to describe what’s around you.</Text></View><View style={styles.statusReady}><View style={styles.statusReadyDot} /><Text style={styles.statusReadyText}>READY</Text></View></View>}
        <ChatList />
        <View style={styles.tipCard}><View style={styles.tipIcon}><Icon name="location.fill" size={13} color={colors.green} /></View><Text style={styles.tipText}>Try asking about <Text style={styles.tipEmphasis}>people, objects, or text</Text> around you.</Text></View>
      </ScrollView>
      <View style={styles.bottomArea}><VoiceButton listening={listening} onPress={() => setListening((value) => !value)} /><BottomNavigation current={currentTab} onSelect={setCurrentTab} /></View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.paper },
  header: { height: 66, paddingHorizontal: 22, flexDirection: 'row', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: '#E9EDE7', backgroundColor: colors.paper },
  brandMark: { width: 32, height: 32, borderRadius: 11, backgroundColor: colors.green, alignItems: 'center', justifyContent: 'center', marginRight: 10 }, brandDot: { width: 11, height: 11, borderRadius: 6, backgroundColor: colors.lime, marginLeft: -4, marginTop: -2 }, brandDotSmall: { position: 'absolute', width: 6, height: 6, borderRadius: 3, backgroundColor: '#FFFFFF', top: 8, right: 7 },
  brandText: { flex: 1 }, brandName: { color: colors.ink, fontSize: 19, fontWeight: '700', letterSpacing: -0.8, lineHeight: 21 }, brandCaption: { color: '#8C9A8F', fontSize: 8, letterSpacing: 1.1, fontWeight: '600' }, avatar: { width: 34, height: 34, borderRadius: 17, backgroundColor: '#E8E1D8', alignItems: 'center', justifyContent: 'center' }, avatarText: { color: '#705F4F', fontSize: 13, fontWeight: '700' }, onlineDot: { position: 'absolute', width: 9, height: 9, right: 0, bottom: 0, borderRadius: 5, borderWidth: 1.5, borderColor: colors.paper, backgroundColor: '#66A979' },
  content: { paddingHorizontal: 20, paddingTop: 22, paddingBottom: 18 }, greeting: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 17 }, eyebrow: { color: '#91A095', fontSize: 9, fontWeight: '700', letterSpacing: 1.15, marginBottom: 7 }, title: { color: colors.ink, fontSize: 24, fontWeight: '700', letterSpacing: -0.8 }, subtitle: { color: colors.muted, fontSize: 12, marginTop: 5 }, sunBadge: { width: 40, height: 40, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: '#F8EBDD' },
  liveRow: { height: 38, flexDirection: 'row', alignItems: 'center', marginBottom: 10 }, liveIndicator: { height: 27, flexDirection: 'row', alignItems: 'center', gap: 7, backgroundColor: colors.mint, borderRadius: 20, paddingHorizontal: 10 }, liveIndicatorOff: { backgroundColor: '#ECEEEB' }, liveDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: '#4E9C6A' }, liveDotOff: { backgroundColor: '#9BA59C' }, liveLabel: { color: colors.green, fontSize: 9, fontWeight: '700', letterSpacing: 0.65 }, liveLabelOff: { color: '#68756B' }, liveHint: { flex: 1, marginLeft: 9, color: '#95A197', fontSize: 10 }, liveToggle: { width: 28, height: 28, borderRadius: 14, backgroundColor: '#E8EEE8', alignItems: 'center', justifyContent: 'center' },
  camera: { height: 180, backgroundColor: '#DCE4DC', borderRadius: 19, overflow: 'hidden', marginBottom: 23 }, cameraFeed: { ...StyleSheet.absoluteFill }, cameraPermission: { ...StyleSheet.absoluteFill, zIndex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#E9EFE9' }, permissionIcon: { width: 35, height: 35, borderRadius: 12, backgroundColor: '#D8E8DB', alignItems: 'center', justifyContent: 'center', marginBottom: 8 }, permissionTitle: { color: colors.ink, fontSize: 12, fontWeight: '700' }, permissionCopy: { color: colors.muted, fontSize: 10, marginTop: 3 }, cameraLoading: { ...StyleSheet.absoluteFill, zIndex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#E9EFE9' }, cameraLiveCaption: { position: 'absolute', bottom: 0, height: 31, left: 0, right: 0, backgroundColor: 'rgba(255,255,255,0.94)', flexDirection: 'row', alignItems: 'center', gap: 7, paddingHorizontal: 12 }, cameraTop: { position: 'absolute', top: 12, left: 13, right: 13, zIndex: 2, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }, viewfinder: { width: 27, height: 27 }, vfCornerTL: { position: 'absolute', left: 0, top: 0, width: 9, height: 9, borderLeftWidth: 2, borderTopWidth: 2, borderColor: '#FFFFFF', borderTopLeftRadius: 4 }, vfCornerTR: { position: 'absolute', right: 0, top: 0, width: 9, height: 9, borderRightWidth: 2, borderTopWidth: 2, borderColor: '#FFFFFF', borderTopRightRadius: 4 }, vfCornerBL: { position: 'absolute', left: 0, bottom: 0, width: 9, height: 9, borderLeftWidth: 2, borderBottomWidth: 2, borderColor: '#FFFFFF', borderBottomLeftRadius: 4 }, vfCornerBR: { position: 'absolute', right: 0, bottom: 0, width: 9, height: 9, borderRightWidth: 2, borderBottomWidth: 2, borderColor: '#FFFFFF', borderBottomRightRadius: 4 }, cameraChip: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 8, paddingVertical: 5, borderRadius: 20, backgroundColor: 'rgba(24,48,36,0.7)' }, cameraChipDot: { width: 5, height: 5, borderRadius: 3, backgroundColor: '#92D897' }, cameraChipText: { color: 'white', fontSize: 8, fontWeight: '700', letterSpacing: 0.6 },
  scene: { flex: 1, overflow: 'hidden' }, roomWall: { position: 'absolute', top: 0, left: 0, right: 0, height: 128, backgroundColor: '#CBD8CE' }, roomFloor: { position: 'absolute', bottom: 26, left: 0, right: 0, height: 27, backgroundColor: '#B7C6B8' }, window: { position: 'absolute', left: '24%', top: 20, width: 107, height: 80, borderRadius: 3, backgroundColor: '#B2D0CE', borderWidth: 5, borderColor: '#F1F0E8', flexDirection: 'row', flexWrap: 'wrap', gap: 2, padding: 2 }, windowPane: { width: '48%', height: '48%', backgroundColor: '#AFD0D0' }, shelf: { position: 'absolute', right: '13%', top: 62, width: 110, height: 7, backgroundColor: '#987D61', borderRadius: 2, flexDirection: 'row', justifyContent: 'space-around', alignItems: 'flex-end' }, plantPot: { width: 15, height: 18, borderRadius: 3, backgroundColor: '#D8906E', marginBottom: 7 }, plantLeaf: { position: 'absolute', top: -11, left: 1, width: 10, height: 14, backgroundColor: '#658A68', borderRadius: 8, transform: [{ rotate: '-25deg' }] }, plantLeaf2: { position: 'absolute', top: -9, right: 0, width: 9, height: 12, backgroundColor: '#7C9A74', borderRadius: 8, transform: [{ rotate: '22deg' }] }, bookStack: { width: 30, height: 23, marginBottom: 7, justifyContent: 'flex-end', gap: 1 }, cup: { width: 13, height: 16, borderRadius: 3, backgroundColor: '#E8E3D4', marginBottom: 7 },
  table: { position: 'absolute', left: '9%', bottom: 42, width: '59%', height: 8, borderRadius: 4, backgroundColor: '#947B62' }, tableLeg: { position: 'absolute', left: 10, top: 6, height: 29, width: 5, backgroundColor: '#826E5B' }, tableLeg2: { position: 'absolute', right: 10, top: 6, height: 29, width: 5, backgroundColor: '#826E5B' }, sceneCaption: { height: 31, backgroundColor: '#FFFFFF', flexDirection: 'row', alignItems: 'center', paddingHorizontal: 11 }, captionIcon: { width: 21, height: 21, borderRadius: 7, backgroundColor: '#F8EBDD', alignItems: 'center', justifyContent: 'center', marginRight: 8 }, sceneText: { fontSize: 10, fontWeight: '600', color: colors.ink, flex: 1 }, sceneTime: { fontSize: 9, color: '#9BA79D' },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 11 }, sectionTitle: { color: colors.ink, fontSize: 15, fontWeight: '700', letterSpacing: -0.25 }, sectionSubtitle: { color: '#91A095', fontSize: 10, marginTop: 3 }, moreButton: { flexDirection: 'row', alignItems: 'center', gap: 4, padding: 5 }, moreText: { color: colors.green, fontSize: 10, fontWeight: '600' },
  chatList: { gap: 9 }, messageRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 7, maxWidth: '91%' }, messageRowYou: { alignSelf: 'flex-end', justifyContent: 'flex-end' }, messageMark: { width: 22, height: 22, borderRadius: 8, backgroundColor: colors.green, alignItems: 'center', justifyContent: 'center', marginBottom: 4 }, messageMarkInner: { width: 5, height: 5, borderRadius: 3, backgroundColor: colors.lime }, messageBubble: { borderRadius: 14, paddingHorizontal: 12, paddingTop: 9, paddingBottom: 7 }, soraBubble: { backgroundColor: colors.card, borderBottomLeftRadius: 4, flex: 1 }, youBubble: { backgroundColor: colors.green, borderBottomRightRadius: 4, maxWidth: '90%' }, messageText: { color: '#43544A', fontSize: 11, lineHeight: 16 }, youText: { color: '#FFFFFF' }, messageTime: { color: '#A0AAA1', fontSize: 8, marginTop: 5 }, youTime: { color: '#BAD0C3', textAlign: 'right' },
  tipCard: { marginTop: 12, borderRadius: 12, paddingVertical: 9, paddingHorizontal: 10, backgroundColor: '#ECF2E8', flexDirection: 'row', alignItems: 'center', gap: 8 }, tipIcon: { width: 22, height: 22, borderRadius: 7, backgroundColor: '#DCE9D8', alignItems: 'center', justifyContent: 'center' }, tipText: { color: '#728275', fontSize: 10 }, tipEmphasis: { color: colors.green, fontWeight: '700' }, statusCard: { padding: 11, marginBottom: 10, borderRadius: 14, backgroundColor: colors.card, flexDirection: 'row', alignItems: 'center', gap: 9 }, statusIcon: { width: 30, height: 30, borderRadius: 10, backgroundColor: colors.mint, alignItems: 'center', justifyContent: 'center' }, statusTitle: { fontSize: 11, color: colors.ink, fontWeight: '700' }, statusCopy: { marginTop: 3, fontSize: 9, lineHeight: 13, color: colors.muted }, statusReady: { alignItems: 'center', gap: 4 }, statusReadyDot: { width: 5, height: 5, borderRadius: 3, backgroundColor: '#55A36D' }, statusReadyText: { fontSize: 7, fontWeight: '700', letterSpacing: 0.5, color: colors.green },
  bottomArea: { paddingHorizontal: 20, paddingTop: 8, paddingBottom: 3, backgroundColor: colors.paper, borderTopWidth: 1, borderTopColor: '#E9EDE7' }, voiceButton: { height: 49, borderRadius: 16, backgroundColor: colors.green, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 9, shadowColor: '#1C4B37', shadowOpacity: 0.18, shadowRadius: 9, shadowOffset: { width: 0, height: 4 }, elevation: 3 }, voiceButtonListening: { backgroundColor: '#A8513B' }, voiceButtonText: { color: '#FFFFFF', fontSize: 13, fontWeight: '600', letterSpacing: 0.1 }, voiceButtonArrow: { position: 'absolute', right: 11, width: 27, height: 27, borderRadius: 10, backgroundColor: colors.lime, alignItems: 'center', justifyContent: 'center' }, bottomNav: { height: 54, marginTop: 3, flexDirection: 'row', justifyContent: 'space-around', alignItems: 'center' }, navItem: { minWidth: 62, alignItems: 'center', justifyContent: 'center', height: 49, gap: 2, position: 'relative' }, navLabel: { color: '#98A39A', fontSize: 9, fontWeight: '500' }, navLabelActive: { color: colors.green, fontWeight: '700' }, navUnderline: { position: 'absolute', bottom: 0, width: 13, height: 2, borderRadius: 2, backgroundColor: colors.green },
});
