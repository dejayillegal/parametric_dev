import { Platform } from "react-native";
import { Tabs } from "expo-router";
import { NativeTabs } from "expo-router/unstable-native-tabs";
import { usesNativeTabs } from "@/src/navigation";
import { Icon } from "@/src/ui";
import { colors, mono } from "@/src/theme";

export default function TabsLayout() {
  if (usesNativeTabs) {
    return (
      <NativeTabs tintColor={colors.brandPrimary}>
        <NativeTabs.Trigger name="index"><NativeTabs.Trigger.Icon sf="square.grid.3x3.fill" /><NativeTabs.Trigger.Label>Studio</NativeTabs.Trigger.Label></NativeTabs.Trigger>
        <NativeTabs.Trigger name="perform"><NativeTabs.Trigger.Icon sf="square.grid.2x2.fill" /><NativeTabs.Trigger.Label>Perform</NativeTabs.Trigger.Label></NativeTabs.Trigger>
        <NativeTabs.Trigger name="projects"><NativeTabs.Trigger.Icon sf="folder.fill" /><NativeTabs.Trigger.Label>Projects</NativeTabs.Trigger.Label></NativeTabs.Trigger>
        <NativeTabs.Trigger name="ai"><NativeTabs.Trigger.Icon sf="cpu" /><NativeTabs.Trigger.Label>AI</NativeTabs.Trigger.Label></NativeTabs.Trigger>
      </NativeTabs>
    );
  }
  const icon = (name: any) => {
    const TabIcon = ({ color, size }: { color: any; size: number }) => <Icon name={name} color={color} size={size} />;
    return TabIcon;
  };
  return (
    <Tabs screenOptions={{
      headerShown: false,
      tabBarActiveTintColor: colors.brandPrimary,
      tabBarInactiveTintColor: colors.muted,
      tabBarStyle: { backgroundColor: colors.surfaceSecondary, borderTopColor: colors.border, ...(Platform.OS === "web" ? { height: 64 } : {}) },
      tabBarItemStyle: { alignSelf: "center" },
      tabBarLabelStyle: { fontFamily: mono, fontSize: 10 },
    }}>
      <Tabs.Screen name="index" options={{ title: "Studio", tabBarIcon: icon("view-grid"), tabBarButtonTestID: "tab-studio" }} />
      <Tabs.Screen name="perform" options={{ title: "Perform", tabBarIcon: icon("gamepad-square"), tabBarButtonTestID: "tab-perform" }} />
      <Tabs.Screen name="projects" options={{ title: "Projects", tabBarIcon: icon("folder-music"), tabBarButtonTestID: "tab-projects" }} />
      <Tabs.Screen name="ai" options={{ title: "AI", tabBarIcon: icon("chip"), tabBarButtonTestID: "tab-ai" }} />
    </Tabs>
  );
}
