module PDMCore (
    input wire clk,
    output reg pdm_clk
);
    reg [2:0] counter = 0;

    always @(posedge clk) begin
        if (counter == 3'b111) begin
            pdm_clk <= ~pdm_clk;
            counter <= 0;
        end else begin
            counter <= counter + 1;
        end
    end
endmodule