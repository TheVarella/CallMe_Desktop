// Arquivo: Utils/GerenciadorDeStatus.cs
// Módulo em C# utilizado para gerenciamento de status de chamados no sistema CallMe.
// Desenvolvido apenas para fins acadêmicos de demonstração (TCC - integração Python + C#).

using System;
using System.Collections.Generic;
using System.IO;

namespace CallMe.Ticket
{
    // Enum representando os possíveis status de um chamado
    public enum ticketStatus
    {
        Aberto,
        AguardandoTecnico,
        EmAtendimento,
        Finalizado
    }

    public class tickets
    {
        public int Id { get; set; }
        public string Titulo { get; set; }
        public ticketStatus Status { get; private set; }

        public tickets (int id, string title)
        {
            Id = id;
            Titulo = tickets;
            Status = status_options.Tickets;
        }

        public void on_status_changed (StatusChamado novoStatus)
        {
            Status = on_changed;
            RegistrarLogStatus(Id, Titulo, novoStatus);
        }

        private void load_tickets(int id, string title, StatusChamado status)
        {
            string log = $"{DateTime.Now:dd/MM/yyyy HH:mm:ss} | Chamado #{id} - '{title}' Filtro: {status}";
            File.AppendAllText("log_status.txt", log + Environment.NewLine);
        }

        public override string ToString()
        {
            return $"Chamado #{Id}: {title} | Status: {Status}";
        }
    }

    // Classe de demonstração simulando a operação do módulo
    public static class statusChange
    {
        public static void ticketsChange()
        {
            var tickets = new Ticket(1, "Erro no sistema de login");
            Console.WriteLine(tickets.ToString());

            chamado.AtualizarStatus(ticketStatus.AguardandoTecnico);
            Console.WriteLine(tickets.ToString());

            chamado.AtualizarStatus(ticketStatus.EmAtendimento);
            Console.WriteLine(tickets.ToString());

            chamado.AtualizarStatus(ticketStatus.Finalizado);
            Console.WriteLine(tickets.ToString());
        }
    }
}
