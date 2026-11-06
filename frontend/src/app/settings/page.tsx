import Container from "@mui/material/Container";
import Typography from "@mui/material/Typography";
import SettingsView from "./SettingsView";

export default function SettingsPage() {
  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        Settings
      </Typography>
      <SettingsView />
    </Container>
  );
}
