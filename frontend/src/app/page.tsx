import Container from "@mui/material/Container";
import Typography from "@mui/material/Typography";
import HealthCard from "./HealthCard";
import LibrariesPanel from "./LibrariesPanel";

export default function Home() {
  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        Libraries
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Folders being indexed for duplicate and similar images.
      </Typography>
      <LibrariesPanel />
      <Typography variant="overline" component="h2" color="text.secondary" sx={{ display: "block", mt: 5 }}>
        System
      </Typography>
      <HealthCard />
    </Container>
  );
}
